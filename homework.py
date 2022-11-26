import logging
import os
import sys
import time
from http import HTTPStatus
from logging import StreamHandler
from typing import Any, Dict, List

import requests
import telegram
from dotenv import load_dotenv

import exceptions

load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
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
    """Проверка наличия переменных окружения."""
    for token in PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID:
        if token is None:
            logger.critical('Отсутствуют обязательные переменные окружения')
            return False
    logger.info('Все переменные получены')
    return True


def send_message(bot: telegram.Bot, message: str) -> None:
    """Отправка сообщения."""
    try:
        bot.send_message(
            TELEGRAM_CHAT_ID,
            text=message,
        )
    except Exception as error:
        logger.error(f'Cбой при отправке сообщения в Telegram, {error}')
    logging.debug('Сообщение отправлено')


def get_api_answer(timestamp: int) -> Dict[Any, Any]:
    """Доступность API."""
    payload = {'from_date': timestamp}
    try:
        response = requests.get(url=ENDPOINT, headers=HEADERS, params=payload)
        if response.status_code != HTTPStatus.OK:
            logger.error(
                f'Эндпоинт недоступен. Код ошибки: {response.status_code}'
            )
            response.raise_for_status()
        logger.info('Ответ от API получен')
    except requests.RequestException() as error:
        logger.error(f'Сбой при запросе к эндпоинту: {error}')
        raise requests.RequestException(
            'Проверьте правильный ли ответ приходит от API'
        )

    return response.json()


def check_response(response: Dict[Any, Any]) -> List[Any]:
    """Проверяем ответ API."""
    if isinstance(response, dict):
        if 'current_date' in response and 'homeworks' in response:
            logger.info('Все ключи получены')
            if isinstance(response.get('homeworks'), list):
                return response.get('homeworks')
            raise TypeError(' homeworks должен быть списком')
        logger.error('Необходимый ключ отсутсвует в ответе')
        raise exceptions.MissingKeyError('Ключ "homeworks" отсутствует')
    raise TypeError(' Структура данных не соответствует ожиданиям')


def parse_status(homework: Dict[Any, Any]) -> str:
    """Проверка информации о домашней работе."""
    if homework.get('status') in HOMEWORK_VERDICTS:
        verdict = HOMEWORK_VERDICTS.get(homework.get('status'))
        logger.info('Статус домашней работы обнаружен')
        if 'homework_name' in homework:
            homework_name = homework.get('homework_name')
            return (f'Изменился статус проверки работы "{homework_name}". '
                    f'{verdict}')
        raise exceptions.MissingKeyError('Ключ "homework_name" отсутствует')
    elif homework.get('status') is None:
        logger.debug('Отсутствуют новые статусы домашки')
        raise exceptions.WrongStatusError('Статус None')
    else:
        logger.error('Неожиданный статус домашней работы')
        raise exceptions.WrongStatusError('Статус не документирован')


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
                        bot, parse_status(response.get('homeworks')[0])
                    )
                    timestamp = response['current_date']
                time.sleep(RETRY_PERIOD)
            except Exception as error:
                message = f'Сбой в работе программы: {error}'
                send_message(bot, message)
                time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
