import logging
import os
import sys
import time
from http import HTTPStatus
from logging import StreamHandler
from typing import Dict, List, Union

import requests
import telegram
from dotenv import load_dotenv

from CustomErrors import WrongStatusError

# Делала эти импорты через isort, он всегда их так расставляет

load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600  # 10 * 60
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.',
}

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = StreamHandler(stream=sys.stdout)
logger.addHandler(handler)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)


def check_tokens() -> bool:
    """
    Проверяет, что токены получены.
    Райзит исключение при потере какого-либо токена.
    """
    for token in 'PRACTICUM_TOKEN', 'TELEGRAM_TOKEN', 'TELEGRAM_CHAT_ID':
        if (
            token not in [name for name in globals()]
            or globals()[token] is None
        ):
            logger.critical(
                'Отсутствует обязательная переменная окружения - %s', token,
            )
            raise KeyError(
                'Заданы не все переменные окружения',
            )
    logger.info('Переменные окружения получены')
    return True


def send_message(bot: telegram.Bot, text: str) -> None:
    """Бот отправляет текст сообщения в телеграм."""
    try:
        bot.send_message(
            TELEGRAM_CHAT_ID,
            text=text,
        )
    except Exception:
        logger.exception(
            'Cбой при отправке сообщения в Telegram, %s', Exception,
        )
    logging.debug('Сообщение отправлено')


def get_api_answer(timestamp: int) -> Dict[str, Union[List[Dict], int]]:
    """
    Получает ответ от API.
    Райзит исключение при недоступности эндпоинта
    или других сбоях при запросе к нему.
    """
    try:
        response = requests.get(
            url=ENDPOINT, headers=HEADERS, params={'from_date': timestamp},
        )
        logger.info('Ответ от API получен')
    except requests.RequestException() as error:
        logger.exception('Сбой при запросе к эндпоинту: %s', error)
        raise requests.RequestException(
            'Проверьте правильный ли ответ приходит от API',
        )
    if response.status_code != HTTPStatus.OK:
        logger.error(
            'Эндпоинт недоступен. Код ошибки: %s',
            response.status_code,
        )
        response.raise_for_status()

    return response.json()


def check_response(response: Dict[str, Union[List[Dict], int]]) -> List[Dict]:
    """
    Проверяет, соответствует ли тип входных данных ожидаемому.
    Проверяет наличие всех ожидаемых ключей в ответе.
    Райзит TypeError при несоответствии типа данных,
    KeyError - при отсутствии ожидаемого ключа.
    """
    if isinstance(response, dict):
        if 'current_date' in response and 'homeworks' in response:
            logger.info('Все ключи получены')
            if isinstance(response.get('homeworks'), list):
                return response.get('homeworks')
            raise TypeError(' homeworks должен быть списком')
        logger.error('Необходимый ключ отсутсвует в ответе')
        raise KeyError('Ключ "homeworks" отсутствует')
    raise TypeError(' Структура данных не соответствует ожиданиям')


def parse_status(homework: Dict[str, Union[int, str]]) -> str:
    """Проверка информации о домашней работе."""
    if homework.get('status') in HOMEWORK_VERDICTS:
        verdict = HOMEWORK_VERDICTS.get(homework.get('status'))
        logger.info('Статус домашней работы обнаружен')
        if 'homework_name' in homework:
            homework_name = homework.get('homework_name')
            return (
                f'Изменился статус проверки работы "{homework_name}". '
                f'{verdict}'
            )
        raise KeyError('Ключ "homework_name" отсутствует')
    elif homework.get('status') is None:
        logger.debug('Отсутствуют новые статусы домашки')
        raise WrongStatusError('Статус None')
    else:
        logger.error('Неожиданный статус домашней работы')
        raise WrongStatusError('Статус не документирован')


def main() -> None:
    """Основная логика работы бота."""
    if check_tokens():
        bot = telegram.Bot(token=TELEGRAM_TOKEN)
        timestamp = int(time.time())
        while True:
            try:
                response = get_api_answer(timestamp=timestamp)
                homeworks = check_response(response)
                if len(homeworks) > 0:
                    send_message(
                        bot,
                        parse_status(response.get('homeworks')[0]),
                    )
                    timestamp = response['current_date']
                time.sleep(RETRY_PERIOD)
            except Exception as error:
                message = f'Сбой в работе программы: {error}'
                send_message(bot, message)
                time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
