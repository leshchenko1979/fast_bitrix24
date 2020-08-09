# fast_bitrix24
Высокоуровневый API для Python 3.7+ для быстрого получения данных от Битрикс24 через REST API.

## Основная функциональность
### Удобство кода
- Высокоуровневые списочные методы для сокращения количества необходимого кода. Большинство операций занимают только одну строку кода. Обработка параллельных запросов, упаковка запросов в батчи и многое другое убрано "под капот".
- Позволяет задавать параметры запроса именно в таком виде, как они приведены в [документации к Bitrix24 REST API](https://dev.1c-bitrix.ru/rest_help/index.php). Параметры проверяются на корректность для облегчения отладки.
- Выполнение запросов автоматически сопровождается прогресс-баром из пакета `tqdm`, иллюстрирующим не только количество обработанных элементов, но и прошедшее и оставшееся время выполнения запроса.

### Высокая скорость обмена данными
- На больших списках скорость обмена данными с сервером достигает тысяч элементов в секунду.
- Использование асинхронных запросов через `asyncio` и `aiohttp` позволяет экономить время, делая несколько запросов к серверу параллельно.
- Автоматическая упаковка запросов в батчи сокращает количество требуемых запросов к серверу и ускоряет обмен данными.

### Избежание отказов сервера
- Скорость отправки запросов к серверу Битрикс контролируется для избежания ошибки HTTP `503 Service unavailable`.
- Размера батча контролируется для избежания ошибки HTTP `414 URI too long`.
- Если сервер для сложных запросов начинает возвращать `500 Internal Server Error`, можно в одну строку понизить скорость запроосов.

## Начало
Установите модуль через `pip`:
```shell
pip install fast_bitrix24
```

Далее в python:

```python
from fast_bitrix24 import *

# замените на ваш вебхук для доступа к Bitrix24
webhook = "https://your_domain.bitrix24.ru/rest/1/your_code/"
b = Bitrix(webhook)
```

Методы полученного объекта `b` в дальнейшем используются для взаимодействия с сервером Битрикс24.

## Использование

### `get_all()`

Чтобы получить полностью список сущностей, используйте метод `get_all()`:

```python
# список пользователей
users = b.get_all('user.get')
```

Метод `get_all()` возвращает список, где каждый элемент списка является словарем, описывающим одну сущность из запрощенного списка.

Вы также можете использовать параметр `params`, чтобы кастомизировать запрос:

```python
# список сделок в работе, включая пользовательские поля
deals = b.get_all('crm.deal.get', params={
    'select': ['*', 'UF_*'],
    'filter': {'CLOSED': 'N'}
})
```

### `get_by_ID()`
Если у вас есть список ID сущностей, то вы можете получить их при помощи метода `get_by_ID()`
и использовании методов вида `*.get`:

```python
'''
получим список всех контактов, привязанных к сделкам, в виде
[
    (ID сделки1, [контакт1, контакт2, ...]), 
    (ID сделки2, [контакт1, контакт2, ...]), 
    ...
]
'''

contacts = b.get_by_ID('crm.deal.contact.item.get',
    [d['ID'] for d in deals])
```
Метод `get_by_ID()` возвращает список кортежей вида `(ID, result)`, где `result` - ответ сервера относительно этого `ID`.

### `call()`
Чтобы создавать, изменять или удалять список сущностей, используйте метод `call()`:

```python
# вставим в начало названия всех сделок их ID
tasks = [
    {
        'ID': d['ID'],
        fields: {
            'TITLE': f'{d["ID"]} - {d["TITLE"]}'
        }
    }
    for d in deals
]

b.call('crm.deal.update', tasks)
```
Метод `call()` возвращает список ответов сервера по каждому элементу переданного списка. 

## Класс `Bitrix`
Объект класса `Bitrix ` создаётся, чтобы через него выполнять все запросы к серверу Битрикс24. Внутри объекта ведётся учёт скорости отправки запросов к серверу, поэтому важно, чтобы все запросы приложения отправлялись из одного экземпляра `Bitrix`.

Под капотом все методы класса используют параллельные запросы и автоматическое построение батчей, чтобы ускорить получение данных. 

Все методы будут поднимать исключения класса `aiohttp.ClientError`, если сервер Битрикс вернул HTTP-ошибку, и `RuntimeError`, если код ответа был `200`, но ошибка сдержалась в теле ответа сервера (_да, иногда бывает и такое!_).

Перед обращением к серверу во всех методах происходит проверка корректности самых популярных параметров, передаваемых к серверу, и поднимается `TypeError` при наличии ошибок.

Все методы возвращают список содержимого поля `result` из ответов сервера. При этом этот список результатов _не отсортирован_, и, если вам нужна сортировка, вам нужно сделать ее самостоятельно. 

### Метод ` __init__(self, webhook: str, verbose: bool = True):`
Создаёт экземпляр объекта `Bitrix`.

#### Параметры 
* `webhook: str` - URL вебхука, полученного от сервера Битрикс.
        
* `verbose: bool = True` - показывать прогрессбар при выполнении запроса.

### Метод `get_all(self, method: str, params: dict = None) -> list`
Получить полный список сущностей по запросу method.

`get_all()` самостоятельно обрабатывает постраничные ответы сервера, чтобы вернуть полный список.

#### Параметры
* `method: str` - метод REST API для запроса к серверу.

* `params: dict` - параметры для передачи методу. Используется именно тот формат, который указан в документации к REST API Битрикс24. `get_all()` не поддерживает параметры `start`, `limit` и `order`.

Возвращает полный список сущностей, имеющихся на сервере, согласно заданным методу и параметрам.

### Метод `get_by_ID(self, method: str, ID_list: Sequence, ID_field_name: str = 'ID', params: dict = None) -> list`
Получить список сущностей по запросу `method` и списку ID.

Используется для случаев, когда нужны не все сущности, имеющиеся в базе, а конкретный список поименованных ID, либо в REST API отсутствует способ  получения сущностей одним вызовом.

Например, чтобы получить все контакты, привязанные к сделкам в работе, нужно выполнить следующий код:

```python
deals = b.get_all('crm.deal.get', params={
    'filter': {'CLOSED': 'N'}
})

contacts = b.get_by_ID('crm.deal.contact.item.get',
    [d['ID'] for d in deals])
```

#### Параметры

* `method: str` - метод REST API для запроса к серверу.

* `ID_list: Sequence` - список ID, в отношении которых будут выполняться запросы.

* `ID_field_name` - название поля, в которое будут подставляться значения из списка `ID_list`. По умолчанию `'ID'`.

* `params: dict` - параметры для передачи методу. 
    Используется именно тот формат, который указан в 
    документации к REST API Битрикс24. Если среди параметров,
    указанных в `params`, указан параметр `ID`, то
    поднимается исключение `ValueError`.

Возвращает список кортежей вида:

```
[
    (ID, <результат запроса>), 
    (ID, <результат запроса>), 
    ...
]
```

Первым элементом каждого кортежа будет ID из списка `ID_list`. Вторым элементом каждого кортежа будет результат выполнения запроса относительно этого ID. Это может быть, например, список связанных сущностей или пустой список, если не найдено ни одной привязанной сущности.

`get_by_ID()` гарантированно возвращает список такой же длины, как и поданный на вход `ID_list`.

### Метод `call(self, method: str, item_list: Sequence) -> list`

Вызвать метод REST API по списку. Самый универсальный метод, 
применяемый, когда `get_all` и `get_by_ID` не подходят.

#### Параметры
* `method: str` - метод REST API

* `item_list: Sequence` - список параметров вызываемого метода

`call()` вызывает `method`, последовательно подставляя в параметры запроса все элементы `item_list` и возвращает список ответов сервера для каждого из отправленных запросов.

## Контекстный менеджер `slow`

Иногда, когда серверу Битрикса посылается запрос, отбирающий много ресурсов сервера
(например, на создание 2500 лидов), то сервер не выдерживает даже стандартных
темпов подачи запросов, описанных в официальной документации, возвращая `500 Internal Server Error`
после нескольких первых запросов. 

В такой ситуации помогает замедление запросов при
помощи контекстного менеджера `slow`:

```python
# временно снижаем скорость до 0.2 запроса в секунду
slower_speed = 0.2
with slow(slower_speed):
    b.call('crm.lead.add', [{} for x in range(2500)])

# а теперь несемся с прежней скоростью
leads = b.get_all('crm.lead.list')
...
```

### `slow(requests_per_second: float = 0.5)`
Снижает скорость запросов. По вызовам Bitrix, происходящим внутри выхова этого контекстного менеджера:
* скорость запросов гарантированно не превысит `requests_per_second`
* механика "пула запросов" отключается - считается, что размер пула равен 0, и запросы подаются равномерно

После выхода из контекстного менеджера механика пула восстанавливается, однако пул считается пустым и начинает наполняться с обычной скоростью 2 запроса в секунду.

#### Параметры
* `requests_per_second: float = 0.5` - требуемая замедленная скорость запросов. По умолчанию 0.5 запросов в секунду.

# Советы и подсказки

### А как мне сформировать запрос к Битриксу, чтобы  ...?

1. Поищите в [официальной документации по REST API](https://dev.1c-bitrix.ru/rest_help/).
2. Если на ваш вопрос там нет ответа - попробуйте задать его в [группе "Партнерский REST API" в Сообществе разработчиков Битрикс24](https://dev.bitrix24.ru/workgroups/group/34/).
3. Спросите на [русском StackOverflow](https://ru.stackoverflow.com/questions/tagged/битрикс24).

### Я хочу добавить несколько лидов списком, но получаю ошибку сервера.

Оберните вызов `call()` в `slow`, установив скорость запросов в 1 - 1,3 в секунду:

```python
with slow(1):
    results = b.call('crm.lead.add', tasks)
```

### Я хочу вызвать `call()` только один раз, а не по списку.
Берите параметры вашего вызова, заворачивайте их в список из одного элемента и делайте вызов.

```python
method = 'crm.lead.add'
params = {'fields': {
    'TITLE': 'Чпок'
}}
item_list = [params]
b.call(method, item_list)
```
Результатом будет также список из одного элемента, содержащего ответ сервера.

Однако, если такие вызовы делаются несколько раз, то более эффективно формировать из них список и вызывать `call()` единожды по всему списку.

### Я хочу сделать пакетный вызов через метод REST API `batch`.
Используйте `call()`, как описано выше. При этом вы даже можете использовать результаты одной команды в параметрах следующей, как описано в [официальной документации по методу `batch`](https://dev.1c-bitrix.ru/rest_help/general/batch.php).

### Как сортируются результаты вызова?
Никак. Все обращения к серверу происходят асинхронно и список результатов отсортирован в том порядке, в котором сервер возвращал ответы. Если вам требуется сортировка, то вам нужно делать ее самостоятельно.

Например, для метода `get_all()`:

```python
deals = b.get_all('crm.deal.list')
deals.sort(key = lambda d: int(d['ID']))
```
То же самое касается и методов `get_by_ID()` и `call()` - порядок элементов в списке результатов не совпадает с порядком в списке запросов.

## Как связаться с автором
- e-mail: leshchenko@gmail.com
- telegram: https://t.me/leshchenko1979
- создать новый github issue: https://github.com/leshchenko1979/fast_bitrix24/issues/new