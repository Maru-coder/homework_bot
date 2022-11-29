import logging
import os
import sys
import time
from http import HTTPStatus
from typing import Dict, List, Union

import requests
import telegram
from dotenv import load_dotenv

from exceptions import WrongStatusError

load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600  # перевод 10 минут в секунды. 10 * 60 = 600 секунд
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.',
}

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stdout,
    format='%(asctime)s - %(levelname)s - '
           '%(funcName)s - %(lineno)d - %(message)s',
)


def check_tokens() -> None:
    """
    Проверяет, что токены получены.

    Райзит исключение при потере какого-либо токена.
    """
    missing_tokens = [
        token
        for token in ('PRACTICUM_TOKEN', 'TELEGRAM_TOKEN', 'TELEGRAM_CHAT_ID')
        if token not in globals() or globals()[token] is None
    ]
    if len(missing_tokens) > 0:
        logging.critical(
            'Отсутствуют обязательные токены - %s',
            *missing_tokens,
        )
        raise KeyError(
            f'Не заданы следующие токены '
            f'- {" ".join(str(token) for token in missing_tokens)},',
        )
    logging.info('Все необходимые токены получены')


def send_message(bot: telegram.Bot, text: str) -> None:
    """Бот отправляет текст сообщения в телеграм."""
    try:
        bot.send_message(
            TELEGRAM_CHAT_ID,
            text=text,
        )
    except Exception:
        logging.exception(
            'Cбой при отправке сообщения в Telegram, %s',
            Exception,
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
            url=ENDPOINT,
            headers=HEADERS,
            params={'from_date': timestamp},
        )
    except requests.exceptions.RequestException as error:
        logging.exception('Сбой при запросе к эндпоинту: %s', error)
        raise requests.exceptions.RequestException(
            'Ошибка при запросе к API: %s',
            response.status_code,
        )  # Тут падает тест от яндекса если в блоке эксепта нет статус кода.
        # Начинает писать что requests.exceptions.RequestException
        # в коде не обрабаытвается. поэтому до этого туда и делала скобки,
        # а сейчас добавила статус код сюда. Вот просто если его убрать и
        # выводить сообщение без всего, то тесты уже не проходят
        # Комментарии такого типа после итераций удалю)
    logging.info('Ответ от API получен')
    if response.status_code != HTTPStatus.OK:
        logging.error(
            'Данный эндпоинт недоступен - %s. Код ошибки: %s',
            response.url,
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
    if (
        isinstance(response, dict)
        and all(key for key in ('current_date', 'homeworks'))
        and isinstance(response.get('homeworks'), list)
    ):
        logging.info('Все ключи получены и соответствуют норме')
        return response.get('homeworks')
    raise TypeError('Структура данных не соответствует ожиданиям')


def parse_status(homework: Dict[str, Union[int, str]]) -> str:
    """
    Проверяет статус домашней работы.
    При наличии возвращает сообщение для отправки в Telegram.
    При отсутствии статуса или получении недокументированного статуса
    райзит исключение.
    """
    if homework.get('status') in HOMEWORK_VERDICTS:
        verdict = HOMEWORK_VERDICTS.get(homework.get('status'))
        logging.info('Статус домашней работы обнаружен')
        if 'homework_name' in homework:
            name = homework.get('homework_name')
            return f'Изменился статус проверки работы "{name}". ' f'{verdict}'
        raise KeyError('Ключ "homework_name" отсутствует')
    elif homework.get('status') is None:
        logging.debug('Отсутствуют новые статусы домашки')
        raise WrongStatusError('Статус None')
    else:
        logging.error('Неожиданный статус домашней работы')
        raise WrongStatusError('Статус не документирован')


def main() -> None:
    """Основная логика работы бота."""
    check_tokens()
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    error_message = ''
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
            if error != error_message:
                message = f'Сбой в работе программы: {error}'
                send_message(bot, message)
                error_message = error
                time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
