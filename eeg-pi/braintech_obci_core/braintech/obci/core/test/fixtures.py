import pytest
from braintech.obci.core.broker.broker import Broker
from braintech.obci.core.utils import yield_then_shutdown


@pytest.fixture(scope='session')
def strings_list():
    yield [
        '', ' ', 'abc', '123', ' 123', ' abc ', ' 123 ',
        '\n', '\r', '\a', '\b', '\f', '\t', '\v', '\'', '\"', '`', '\\', '/', '', '\x00', 'a\x00b',
        'ą, ć, ę, ł, ń, ó, ś, ź, ż, Ą, Ć, Ę, Ł, Ń, Ó, Ś, Ź, Ż', '⛱',
        'Ё Ђ Ѓ Є Ѕ І Ї Ј Љ Њ Ћ Ќ Ў Џ А Б В Г Д Е Ж З И Й К Л М Н О П Р С Т У Ф Х Ц Ч'
        ' Ш Щ Ъ Ы Ь Э Ю Я а б в г д е ж з и й к л м н о п р с т у ф х ц ч ш щ ъ ы ь э ю я ё ђ'
        ' ѓ є ѕ і ї ј љ њ ћ ќ ў џ Ѡ ѡ Ѣ ѣ Ѥ ѥ Ѧ ѧ Ѩ ѩ Ѫ ѫ Ѭ ѭ Ѯ ѯ Ѱ ѱ Ѳ ѳ Ѵ ѵ Ѷ ѷ Ѹ ѹ Ѻ ѻ Ѽ ѽ'
        ' Ѿ ѿ Ҁ ҁ ҂ ҃ ...',
        '子曰：「學而時習之，不亦說乎？有朋自遠方來，不亦樂乎？人不知而不慍，不亦君子乎？」',
    ]


@pytest.fixture(scope='session')
def json_data(strings_list):
    dct = {
        'a': 1,
        'b': 2,
        'c': 'abc',
        'd': 1.5,
        'f': {
            'a': 10,
            'b': 11
        },
        'true': True,
        'false': False,
        'null': None,
        'array_1': [1, 2, 3, 4],
        'array_1a': ['1', '2', '3', '4'],
        'array_2': [1.5, 2.5, 3.5, 4.5],
        'array_3': [
            {'a': 'a'},
            {'b': 'b'}
        ],
        'array_3a': [
            {'a': 'a'},
            {'b': 'b'},
            {'c': [1, 2, [3, 4], 5]}
        ],
        'array_4': [1, 2, [3, 4], 5]
    }

    for idx, string in enumerate(strings_list, start=1):
        dct['unicode_{}'.format(idx)] = string

    yield dct


@pytest.fixture(scope='module')
def broker():
    yield from yield_then_shutdown(Broker())
