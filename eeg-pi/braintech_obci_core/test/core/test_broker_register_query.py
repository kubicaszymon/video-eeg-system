# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

import asyncio

import pytest

from braintech.obci.core.broker.broker import Broker
from braintech.obci.core.broker.messages.fields import Field
from braintech.obci.core.broker import messages
from braintech.obci.core.broker.peer import (Peer,
                                             PeerInitUrls,
                                             TooManyRedirectsException,
                                             MultiplePeersAvailable,
                                             QueryAnswerUnknown)

from braintech.obci.core.utils import wait_until_peers_ready


def set_json_data(json_data, obj):
    """Returns json data from fixture.

    To be used in functions when passing another argument is not allowed
    because of API restrictions.
    """
    obj.JSON_DATA = json_data


class _Async_Query1(messages.BaseMessage):
    data = Field(dict)


class _Async_Query2(messages.BaseMessage):
    data = Field(dict)


class _Query1(messages.BaseMessage):
    data = Field(int)


class _Query2(messages.BaseMessage):
    data = Field(str)


class _Query3(messages.BaseMessage):
    data = Field(dict)


class _Q1_Query(messages.BaseMessage):
    data = Field(dict)


class _QA_Query(messages.BaseMessage):
    data = Field(dict)


class _Redirect_Query(messages.BaseMessage):
    data = Field(str)


class _Redirect_Loop_Query(messages.BaseMessage):
    data = Field(str)


class QueryAsyncPeer(Peer):
    JSON_DATA = None

    async def _async1_query_handler(self, _: _Async_Query1) -> _Async_Query1:
        await asyncio.sleep(0)
        return _Async_Query1(data=self.JSON_DATA)

    async def _async2_query_handler(self, _: _Async_Query2) -> _Async_Query2:
        await asyncio.sleep(0)
        return _Async_Query2(data=self.JSON_DATA)

    async def _connections_established(self):
        await super()._connections_established()
        await self.register_query_handler_async(_Async_Query1, self._async1_query_handler)
        await self.register_query_handler_async(_Async_Query2, self._async2_query_handler)

    async def run_tests_coro(self):
        # answered by broker
        assert (await self.query_async(_Query1(data=1))).data == 123
        assert (await self.query_async(_Query2(data='a'))).data == 'abc'
        assert (await self.query_async(_Query3(data={}))).data == self.JSON_DATA

        # answered by single peer
        assert (await self.query_async(_Q1_Query(data={}))).data == self.JSON_DATA

        # answered by two peers
        with pytest.raises(MultiplePeersAvailable):
            await self.query_async(_QA_Query(data={}))

        # redirect queries
        assert (await self.query_async(_Redirect_Query(data='a'))).data == 'kjl'

        with pytest.raises(TooManyRedirectsException):
            assert await self.query_async(_Redirect_Loop_Query(self.id, data='a'))

    async def unregister_q2_coro(self):
        await self.unregister_query_handler_async(_Async_Query2)

    async def unregister_all_coro(self):
        await self.unregister_query_handler_async()

    def run_tests(self):
        # will reraise exception if one was raised by run_tests_coro
        self.create_task(self.run_tests_coro()).exception()

    def unregister_q2(self):
        self.create_task(self.unregister_q2_coro()).exception()

    def unregister_all(self):
        self.create_task(self.unregister_all_coro()).exception()


def run_test(broker_ip_address,
             broker_rep,
             broker_xpub,
             broker_xsub,
             peer_pub,
             peer_rep,
             use_async_lambdas,
             json_data):

    broker = Broker(broker_ip_address, [broker_rep], [broker_xpub], [broker_xsub])

    urls = PeerInitUrls(pub_urls=[peer_pub],
                        rep_urls=[peer_rep],
                        broker_rep_url=broker_rep)

    query1_peer = Peer(urls, '1')
    query2_peer = Peer(urls, '2')
    answer_peer = Peer(broker_ip_address, '3')
    looper_peer = Peer(urls, '4')
    async_peer = QueryAsyncPeer(urls, '5')

    all_peers = [query1_peer, query2_peer, answer_peer, looper_peer, async_peer]

    print('waiting for peers ...', end='')
    wait_until_peers_ready([broker] + all_peers)
    print('done')

    def wrap_lambda(lambda_func):
        if use_async_lambdas:
            async def wrapper(*args, **kwargs):
                await asyncio.sleep(0)
                return lambda_func(*args, **kwargs)
            return wrapper
        else:
            return lambda_func

    # query types answered directly by broker
    broker.register_message_handler(_Query1, wrap_lambda(lambda _: _Query1(sender='0', data=123)))
    broker.register_message_handler(_Query2, wrap_lambda(lambda _: _Query2(sender='0', data='abc')))
    broker.register_message_handler(_Query3, wrap_lambda(lambda _: _Query3(sender='0', data=json_data)))

    def register_query_handler(peer, query_type):
        peer.register_query_handler(query_type, lambda _: query_type(sender=peer.id, data=json_data))

    print('query types answered directly by single peer')
    register_query_handler(query1_peer, _Q1_Query)

    # query types answered directly by two peers
    register_query_handler(query1_peer, _QA_Query)
    register_query_handler(query2_peer, _QA_Query)

    url_answer_peer = list(answer_peer._rep_urls)  # sets are not JSON serializable
    url_looper_peer = list(looper_peer._rep_urls)

    # redirect query types
    query1_peer.register_query_handler(
        _Redirect_Query,
        lambda _: _Redirect_Query(sender=query1_peer.id, data='kjl')
    )

    query1_peer.register_query_handler(
        _Redirect_Loop_Query,
        lambda _: messages.RedirectMsg(sender=query1_peer.id, peers=[(query1_peer.id, url_looper_peer)])
    )

    answer_peer.register_message_handler(
        _Redirect_Query,
        wrap_lambda(lambda _: _Redirect_Query(sender=answer_peer.id, data='kjl')))

    answer_peer.register_message_handler(
        _Redirect_Loop_Query,
        wrap_lambda(lambda _: messages.RedirectMsg(sender=answer_peer.id,
                                                   peers=[(answer_peer.id, url_answer_peer)])))

    looper_peer.register_message_handler(
        _Redirect_Loop_Query,
        wrap_lambda(lambda _: messages.RedirectMsg(sender=looper_peer.id,
                                                   peers=[(looper_peer.id, url_looper_peer)])))

    # answered by broker
    assert query1_peer.query(_Query1(sender=query1_peer.id, data=1)).data == 123
    assert query1_peer.query(_Query2(sender=query1_peer.id, data='a')).data == 'abc'
    assert query1_peer.query(_Query3(sender=query1_peer.id, data={})).data == json_data

    # answered by single peer
    assert query1_peer.query(_Q1_Query(sender=query1_peer.id, data={})).data == json_data

    # answered by two peers
    try:
        query1_peer.query(_QA_Query(sender=query1_peer.id, data={}))
    except MultiplePeersAvailable as ex:
        peer_urls = [url for _, url in ex.peers]
        assert set(peer_urls) <= set(query1_peer._rep_urls.union(query2_peer._rep_urls))
    else:
        assert False, 'Must throw exception.'

    # redirect queries
    assert query1_peer.query(_Redirect_Query(sender=query1_peer.id, data='a')).data == 'kjl'

    with pytest.raises(TooManyRedirectsException):
        query1_peer.query(_Redirect_Loop_Query(sender=query1_peer.id, data='a'))

    # test initial_peer parameter
    assert query1_peer.query(_Redirect_Query(sender=query1_peer.id,
                                             data='a'), initial_peer=url_answer_peer).data == 'kjl'

    with pytest.raises(TooManyRedirectsException):
        answer_peer.query(_Redirect_Loop_Query(sender=answer_peer.id,
                                               data='a'), initial_peer=url_looper_peer)

    with pytest.raises(TooManyRedirectsException):
        looper_peer.query(_Redirect_Loop_Query(sender=looper_peer.id,
                                               data='a'), initial_peer=url_answer_peer)

    # run tests from example peer
    async_peer.run_tests()
    assert query1_peer.query(_Async_Query1(query1_peer.id, data={})).data == json_data
    assert query1_peer.query(_Async_Query2(query1_peer.id, data={})).data == json_data

    async_peer.unregister_q2()
    assert query1_peer.query(_Async_Query1(query1_peer.id, data={})).data == json_data
    with pytest.raises(QueryAnswerUnknown):
        query1_peer.query(_Async_Query2(query1_peer.id, data={}))

    async_peer.unregister_all()
    with pytest.raises(QueryAnswerUnknown):
        query1_peer.query(_Async_Query1(query1_peer.id, data={}))
    with pytest.raises(QueryAnswerUnknown):
        query1_peer.query(_Async_Query2(query1_peer.id, data={}))

    # test unregister_query_handler
    query1_peer.unregister_query_handler(_Redirect_Query(query1_peer.id, data='a'))
    query1_peer.unregister_query_handler(_Redirect_Loop_Query(query1_peer.id, data='a'))

    with pytest.raises(QueryAnswerUnknown):
        query1_peer.query(_Redirect_Query(query1_peer.id, data='a'))
    with pytest.raises(QueryAnswerUnknown):
        query1_peer.query(_Redirect_Loop_Query(query1_peer.id, data='a'))

    query2_peer.unregister_query_handler()

    assert query2_peer.query(_QA_Query(query2_peer.id, data={})).data == json_data
    assert query1_peer.query(_QA_Query(query1_peer.id, data={})).data == json_data

    # shutdown
    for p in all_peers:
        p.shutdown()

    broker.shutdown()


params = {
    'broker_ip_address': '127.0.0.1:23821',
    'broker_rep': 'tcp://127.0.0.1:20001',
    'broker_xpub': 'tcp://127.0.0.1:20002',
    'broker_xsub': 'tcp://127.0.0.1:20003',
    'peer_pub': 'tcp://127.0.0.1:*',
    'peer_rep': 'tcp://127.0.0.1:*'
}


def test_query_1(json_data):
    set_json_data(json_data, QueryAsyncPeer)
    params.update(json_data=QueryAsyncPeer.JSON_DATA, use_async_lambdas=False)
    run_test(**params)


def test_query_2(json_data):
    set_json_data(json_data, QueryAsyncPeer)
    params.update(json_data=QueryAsyncPeer.JSON_DATA, use_async_lambdas=True)
    run_test(**params)
