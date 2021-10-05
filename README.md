# fast_bitrix24
API wrapper для Питона для быстрого получения данных от Битрикс24 через REST API.

![Статистика тестов](https://github.com/leshchenko1979/fast_bitrix24/workflows/Tests%20on%20push%20%28Ubuntu%2FPython%203.9%29/badge.svg)
[![Статистика загрузок](https://img.shields.io/pypi/dm/fast-bitrix24.svg)](https://pypistats.org/packages/fast-bitrix24)
[![Sourcery](https://img.shields.io/badge/Sourcery-enabled-brightgreen)](https://sourcery.ai)


## Основная функциональность

### Высокая скорость обмена данными

![Тест скорости](speed_test.gif)

- На больших списках скорость обмена данными с сервером достигает тысяч элементов в секунду.
- Автоматическая упаковка запросов в батчи сокращает количество требуемых запросов к серверу и ускоряет обмен данными.
- Батчи отправляются на сервер не последовательно, а параллельно.
- Продвинутые стратегии работы с постраничным доступом ускоряют выгрузку на порядки (см. [результаты тестов](https://github.com/leshchenko1979/fast_bitrix24/discussions/113)).

### Избежание отказов сервера
- Автоматический autothrottling - если сервер возвращает ошибки, скорость автоматически понижается.
- Если сервер для сложных запросов начинает возвращать ошибки, можно в одну строку понизить скорость запроосов.

### Удобство кода
- Высокоуровневые списочные методы для сокращения количества необходимого кода. Большинство операций занимают только одну строку кода. Обработка параллельных запросов, упаковка запросов в батчи и многое другое убрано "под капот".
- Позволяет задавать параметры запроса именно в таком виде, как они приведены в [документации к Bitrix24 REST API](https://dev.1c-bitrix.ru/rest_help/index.php). Параметры проверяются на корректность для облегчения отладки.
- Выполнение запросов автоматически сопровождается прогресс-баром из пакета `tqdm`, иллюстрирующим не только количество обработанных элементов, но и прошедшее и оставшееся время выполнения запроса.

### Синхронный и асинхронный клиенты
- Наличие асинхронного клиента позволяет использовать библиотеку для написания веб-приложений (например, телеграм-ботов).

## Начало
Установите модуль через `pip`:
```shell
pip install fast-bitrix24
```

Далее в python:

```python
from fast_bitrix24 import Bitrix

# замените на ваш вебхук для доступа к Bitrix24
webhook = "https://your_domain.bitrix24.ru/rest/1/your_code/"
b = Bitrix(webhook)
```

Методы полученного объекта `b` в дальнейшем используются для взаимодействия с сервером Битрикс24.

## Использование

### `get_all()`

Чтобы получить полностью список сущностей, используйте метод `get_all()`:

```python
# список лидов
leads = b.get_all('crm.lead.list')
```

Метод `get_all()` возвращает список, где каждый элемент списка является словарем, описывающим одну сущность из запрошенного списка.

Вы также можете использовать параметр `params`, чтобы кастомизировать запрос:

```python
# список сделок в работе, включая пользовательские поля
deals = b.get_all(
    'crm.deal.list',
    params={
        'select': ['*', 'UF_*'],
        'filter': {'CLOSED': 'N'}
})
```

Если у вас есть необходимость быстро выгрузить большие объемы информации (значения всех полей в длинных списках - в 20+ тыс. элементов), то используйте метод `list_and_get()` (см. [документацию по методу](https://github.com/leshchenko1979/fast_bitrix24#метод-list_and_getself-method_branch-str---dict)).

### `get_by_ID()`
Если у вас есть список ID сущностей, то вы можете получить их свойства при помощи метода `get_by_ID()`
и использовании методов вида `*.get`:

```python
'''
получим список всех контактов, привязанных к сделкам, в виде
{
    ID_сделки_1: [контакт_1, контакт_2, ...],
    ID_сделки_2: [контакт_1, контакт_2, ...],
    ...
}
'''

contacts = b.get_by_ID(
    'crm.deal.contact.items.get',
    [d['ID'] for d in deals])
```
Метод `get_by_ID()` возвращает словарь с элементами вида `ID: result`, где `result` - ответ сервера относительно этого `ID`.

### `call()`
Чтобы создавать, изменять или удалять список сущностей, используйте метод `call()`:

```python
# вставим в начало названия всех сделок их ID
tasks = [
    {
        'ID': d['ID'],
        'fields': {
            'TITLE': f'{d["ID"]} - {d["TITLE"]}'
        }
    }
    for d in deals
]

b.call('crm.deal.update', tasks)
```
Метод `call()` возвращает список ответов сервера по каждому элементу переданного списка.

### `call_batch()`
Если вы хотите вызвать пакетный метод, используйте `call_batch()`:

```python
results = b.call_batch ({
    'halt': 0,
    'cmd': {
        'deals': 'crm.deal.list', # берем список сделок
        # и берем список дел по первой из них
        'activities': 'crm.activity.list?filter[ENTITY_TYPE]=3&filter[ENTITY_ID]=$result[deals][0][ID]'
    }
})

```
### Асинхронные вызовы
Если требуется использование бибилиотеки в асинхронном коде, то вместо клиента `Bitrix()` создавайте клиент класса `BitrixAsync()`:
```python
from fast_bitrix24 import BitrixAsync
b = BitrixAsync(webhook)
```
Все методы у него - синхронные аналоги методов из `Bitrix()`, описанных выше:
```python
leads = await b.get_all('crm.lead.list')
```
## Как это работает
1. Перед обращением к серверу во всех методах класса `Bitrix` происходит проверка корректности самых популярных параметров, передаваемых к серверу, и поднимаются исключения `TypeError` и `ValueError` при наличии ошибок.
2. Cоздаются запросы на получение всех элементов из запрошенного списка.
3. Созданные запросы упаковываются в батчи по 50 запросов в каждом.
4. Полученные батчи параллельно отправляются на сервер с регулировкой скорости запросов (см. ниже "Как fast_bitrix24 регулирует скорость запросов").
5. Ответы (содержимое поля `result`) собираются в единый плоский список и возвращаются пользователю.
    - Поднимаются исключения класса `aiohttp.ClientError`, если сервер Битрикс вернул HTTP-ошибку, и `RuntimeError`, если код ответа был `200`, но ошибка сдержалась в теле ответа сервера.
    - Происходит сортировка ответов (кроме метода `get_all()`) - порядок элементов в списке результатов совпадает с порядком соответствующих запросов в списке запросов.

В случае с методом `get_all()` пункт 2 выше выглядит немного сложнее:
  - `get_all()` делает первый запрос к серверу Битрикс24 с указанным методом и параметрами.
  - Сервер возвращает первую страницу (50 элементов) и параметр `total` - общее количество элементов, найденных по запросу.
  - Исходя из полученного общего количества элементов, создаются запросы на каждую из страниц (всего `total // 50 - 1` запросов), необходимых для получения всех запрошенных элементов.

В связи с тем, что выполнение `get_all()` по длинным спискам может занимать долгое время, в течение которого пользователи могут добавлять новые элементы в список, может возникнуть ситуация, когда общее полученное количество элементов может не соответствовать изначальному значению `total`. В таких случаях будет выдано стандартное питоновское предупреждение (`warning`).

### Как `fast_bitrix24` регулирует скорость запросов
По умолчанию `fast_bitrix24` игнорирует официальные ограничения Битрикс24 по скорости запросов (см. ниже "Официальная политика Битрикс24 по скорости запросов") и вместо этого начинает снижать скорость запросов, если сервер начинает возвращать ошибки (autothrottling). Подобный подход позволяет на порядки увеличить скорость получения данных (см. [тесты скорости](https://github.com/leshchenko1979/fast_bitrix24/blob/master/speed_tests/strategies.ipynb)).

Чтобы соблюдать официальные правила, при создании экземпляра класса `Bitrix` укажите параметр `respect_velocity_policy=True`.
### Официальная политика Битрикс24 по скорости запросов
1. Существует пул из 50 запросов, которые можно направить без ожидания.
2. Пул пополняется со скоростью 2 запроса в секунду.
3. При исчерпании пула и несоблюдении режима ожидания сервер возвращает ошибку.

## Подробный справочник по классу `Bitrix`
Объект класса `Bitrix` создаётся, чтобы через него выполнять все запросы к серверу Битрикс24.

Внутри объекта ведётся учёт скорости отправки запросов к серверу, поэтому важно, чтобы все запросы приложения в отношении одного аккаунта с одного IP-адреса отправлялись из одного экземпляра `Bitrix`.

### Метод ` __init__(self, webhook: str, verbose: bool = True, respect_velocity_policy: bool = False, client: aiohttp.ClientSession = None):`
Создаёт экземпляр объекта `Bitrix`.

#### Параметры
* `webhook: str` - URL вебхука, полученного от сервера Битрикс.
* `verbose: bool = True` - показывать прогрессбар при выполнении запроса.
* `respect_velocity_policy: bool = False` - соблюдать политику Битрикса о скорости запросов.
* `client: aiohttp.ClientSession = None` - использовать для HTTP-вызовов клиента, инициализированного и настроенного пользователем.

### Метод `get_all(self, method: str, params: dict = None) -> list | dict`
Получить полный список сущностей по запросу `method`.

`get_all()` самостоятельно обрабатывает постраничные ответы сервера, чтобы вернуть полный список (подробнее см. "Как это работает" выше).

#### Параметры
* `method: str` - метод REST API для запроса к серверу.

* `params: dict` - параметры для передачи методу. Используется именно тот формат, который указан в документации к REST API Битрикс24. `get_all()` не поддерживает параметры `start`, `limit` и `order`.

Возвращает полный список сущностей, имеющихся на сервере, согласно заданным методу и параметрам.

### Метод `get_by_ID(self, method: str, ID_list: Iterable, ID_field_name: str = 'ID', params: dict = None) -> dict`
Получить список сущностей по запросу `method` и списку ID.

Используется для случаев, когда нужны не все сущности, имеющиеся в базе, а конкретный список поименованных ID, либо в REST API отсутствует способ получения сущностей одним вызовом.

Например, чтобы получить все контакты, привязанные к сделкам в работе, нужно выполнить следующий код:

```python
deals = b.get_all(
    'crm.deal.list',
    params={'filter': {'CLOSED': 'N'}})

contacts = b.get_by_ID(
    'crm.deal.contact.item.get',
    [d['ID'] for d in deals])
```

#### Параметры

* `method: str` - метод REST API для запроса к серверу.

* `ID_list: Iterable` - список ID, в отношении которых будут выполняться запросы.

* `ID_field_name: str` - название поля, в которое будут подставляться значения из списка `ID_list`. По умолчанию `'ID'`.

* `params: dict` - параметры для передачи методу.
    Используется именно тот формат, который указан в
    документации к REST API Битрикс24. Если среди параметров,
    указанных в `params`, указан параметр `ID`, то
    поднимается исключение `ValueError`.

Возвращает словарь вида:

```python
{
    ID_1: результат_выполнения_запроса_по_ID_1,
    ID_2: результат_выполнения_запроса_по_ID_2,
    ...
}
```

Ключом каждого элемента возвращаемого словаря будет ID из списка `ID_list`. Значением будет результат выполнения запроса относительно этого ID. Это может быть, например, список связанных сущностей или пустой список, если не найдено ни одной привязанной сущности.

### Метод `list_and_get(self, method_branch: str, ID_field_name='ID') -> dict`
Скачать список всех ID при помощи метода `method_branch + '.list'`,
а затем значения всех полей всех элементов при помощи метода `method_branch + '.get'`. `method_branch` - группа методов, в которой есть подметоды `*.list` и `*.get`, например `crm.lead` или `tasks.task`.

Например:
```python
all_lead_info = b.list_and_get('crm.lead')
```

Подобный подход показывает на порядок большую скорость
получения больших объемов данных (полный набор полей
на списках более 20 тыс. элементов), чем `get_all()`
с параметром `'select': ['*', 'UF_*']`.
См. [сравнение скоростей разных стратегий получения данных](https://github.com/leshchenko1979/fast_bitrix24/discussions/113).

#### Параметры
* `method_branch: str` - группа методов к использованию, например,
"crm.lead".
* `ID_field_name='ID'` - имя поля, в котором метод *.get принимает
идентификаторы элементов (например, `'ID'` для метода `crm.lead.get`)

Возвращает полное содержимое всех элементов в виде, используемом
функцией `get_by_ID()` - словарь следующего вида:
```
{
    ID_1: <словарь полей сущности с ID_1>,
    ID_2: <словарь полей сущности с ID_2>,
    ...
}
```
#### Ограничения
`list_and_get()` не работает с теми группами методов, которые
не поддерживают единое название поля с идентификатором
в параметрах и результатах методов `*.list` и `*.get`.

Например, `tasks.task.list` в результатах идентификатор задачи
возвращает в поле `ID`, но `tasks.task.get` принимает
идентификаторы задач в поле `taskId`.
### Метод `call(self, method: str, items: dict | Iterable[dict]) -> dict | list[dict]`

Вызвать метод REST API. Самый универсальный метод,
применяемый, когда `get_all` и `get_by_ID` не подходят.

#### Параметры
* `method: str` - метод REST API

* `items: dict | Iterable[dict]` - параметры вызываемого метода. Может быть списком, и тогда метод будет вызван для каждого элемента списка, а может быть одним словарем параметров для единичного вызова.

`call()` вызывает `method`, последовательно подставляя в параметры запроса все элементы `items`, и возвращает список ответов сервера для каждого из отправленных запросов. Либо, если `items` - не список, а словарь с параметрами, то происходит единичный вызов и возвращается его результат.


### Метод `call_batch(self, params: dict) -> dict`

Вызвать метод `batch` ([см. официальную документацию по методу `batch`](https://dev.1c-bitrix.ru/rest_help/general/batch.php)).

Поддерживается примение результатов выполнения одной команды в следующей при помощи ключевого слова `$result`:

```python
results = b.call_batch({
    'halt': 0,
    'cmd': {
        'deals': 'crm.deal.list', # берем список сделок
        # и берем список дел по первой из них
        'activities': 'crm.activity.list?filter[ENTITY_TYPE]=3&filter[ENTITY_ID]=$result[deals][0][ID]'
    }
})
```

Возвращает словарь вида:
```python
{
    'имя_команды_1': результаты_выполнения_команды_1,
    'имя_команды_1': результаты_выполнения_команды_1,
    ...
}
```
### Контекстный менеджер `slow(max_concurrent_requests: int = 1)`
Ограничивает количество одновременно выполняемых запросов к серверу Bitrix.

Иногда, когда серверу Битрикса посылается запрос, отбирающий много ресурсов сервера
(например, на создание 2500 лидов), то сервер не выдерживает даже стандартных
темпов подачи запросов, описанных в официальной документации, либо возвращая
`500 Internal Server Error` после нескольких первых запросов, либо вылетая по таймауту
или разрыву соединения.

В такой ситуации помогает введение ограничений при
помощи контекстного менеджера `slow`:

```python
# временно ограничиваем скорость
# до 5 параллельно выполняемых запросов
max_concurrent_requests = 5
with b.slow(max_concurrent_requests):
    b.call('crm.lead.add', [{'NAME': x} for x in range(2500)])

# а теперь несемся с прежней скоростью
leads = b.get_all('crm.lead.list')
...
```
#### Параметры
* `max_concurrent_requests: int = 1` - макимальное количество одновременных запросов к серверу (по умолчанию 1).

# Советы и подсказки

### А как мне сформировать запрос к Битриксу, чтобы  ...?

1. Поищите в [официальной документации по REST API](https://dev.1c-bitrix.ru/rest_help/).
1. Если на ваш вопрос там нет ответа - попробуйте задать его в [группе "Партнерский REST API" в Сообществе разработчиков Битрикс24](https://dev.bitrix24.ru/workgroups/group/34/).
1. Спросите в Телеграме в [группе разработчиков Битрикс24](https://t.me/bit24dev).
1. Спросите в Телеграме в [группе пользователей fast_bitrix24](https://t.me/fast_bitrix24).
1. Спросите на [русском StackOverflow](https://ru.stackoverflow.com/questions/tagged/битрикс24).

### Я хочу добавить несколько лидов списком, но получаю ошибку сервера.

Оберните вызов `call()` в `slow`:

```python
with b.slow():
    results = b.call('crm.lead.add', tasks)
```

### Я хочу вызвать `call()` только один раз, а не по списку.
Передавайте параметры запроса методу `call()`, он может делать как запросы по списку, так и единичный запрос:

```python
method = 'crm.lead.add'
params = {'fields': {'TITLE': 'Чпок'}}
b.call(method, params)
```
Результатом будет ответ сервера по этому одному элементу.

Однако, если такие вызовы делаются несколько раз, то более эффективно формировать из них список и вызывать `call()` единожды по всему списку.

### Как сортируются результаты при вызове `get_all()`?
Пока что никак.

Все обращения к серверу происходят асинхронно и список результатов отсортирован в том порядке, в котором сервер возвращал ответы. Если вам требуется сортировка, то вам нужно делать ее самостоятельно, например:

```python
deals = b.get_all('crm.deal.list')
deals.sort(key = lambda d: int(d['ID']))
```

### Я использую `get_all()` для получения всех полей всех элементов списка, но это происходит слишком долго. Как ускорить этот процесс?
Попробуйте применить метод `list_and_get()` - он стабильно показывает на порядок лучшие результаты на больших объемах информации.

См. [результаты тестов](https://github.com/leshchenko1979/fast_bitrix24/discussions/113).

### Я получаю ошибку сертификата SSL. Что делать?
Если вы получаете `SSLCertVerificationError` / `CERTIFICATE_VERIFY_FAILED`, попробуйте отключить верификацию сертификата SSL. При инициализации передайте в `Bitrix` / `BitrixAsync` параметр `client`,  где будет инициализированный вами экземпляр `aiohttp.ClientSession`, где будет отключена верификация SSL:
```python
import aiohttp
from fast_bitrix24 import Bitrix

connector = aiohttp.TCPConnector(verify_ssl=False)
client = aiohttp.ClientSession(connector=connector)
b = Bitrix(webhook, client=client)
```

## Как связаться с автором
- telegram: https://t.me/fast_bitrix24
- создать новый github issue: https://github.com/leshchenko1979/fast_bitrix24/issues/new
