# Copyright (c) 2016-2018 Braintech Sp. z o.o. [Ltd.] <http://www.braintech.pl>
# All rights reserved.

import asyncio
import pathlib

from braintech.obci.core import utils
from braintech.obci.experiment import messages


class TestReusableSignalSaver:
    def test_starting_saving(self, broker, reusable_signal_saver, tmpdir):
        self._start_saving(broker, reusable_signal_saver, path=str(tmpdir))

    def test_setting_path_without_prefix(self, broker, reusable_signal_saver, tmpdir):
        self._start_saving(broker, reusable_signal_saver, path=str(tmpdir))
        assert reusable_signal_saver.get_param('save_file_path') == str(tmpdir)
        assert reusable_signal_saver.get_param('save_file_name') == 'default'

    def test_setting_path_with_filename_prefix(self, broker, reusable_signal_saver, tmpdir):
        self._start_saving(broker, reusable_signal_saver, path=str(tmpdir),
                           files_prefix='dreamy_eyez')
        assert reusable_signal_saver.get_param('save_file_path') == str(tmpdir)
        assert reusable_signal_saver.get_param('save_file_name') == 'dreamy_eyez'

    def test_error_on_double_starting(self, broker, reusable_signal_saver, tmpdir):
        dir2 = tmpdir.mkdir('whatever')
        self._start_saving(broker, reusable_signal_saver, path=str(tmpdir))
        message = messages.StartSavingSignal(
            save_file_path=str(dir2),
            save_file_name='',
        )
        result = _run_synchronously(reusable_signal_saver, reusable_signal_saver._start_saving_signal(message))
        assert type(result) == messages.SignalSavingError
        assert reusable_signal_saver._session_is_active
        assert reusable_signal_saver.is_running
        assert reusable_signal_saver.get_param('save_file_path') == str(tmpdir)

    def test_stopping(self, broker, reusable_signal_saver, tmpdir):
        self._start_saving(broker, reusable_signal_saver, path=str(tmpdir))
        self._stop_saving(reusable_signal_saver)

    def test_error_on_stopping_not_started(self, broker, reusable_signal_saver):
        utils.wait_until_peers_ready([broker, reusable_signal_saver], timeout=3)
        assert not reusable_signal_saver._session_is_active
        assert not reusable_signal_saver.is_running
        message = messages.StopSavingSignal()
        result = _run_synchronously(reusable_signal_saver, reusable_signal_saver._stop_saving_signal(message))
        assert type(result) == messages.SignalSavingError
        assert not reusable_signal_saver._session_is_active
        assert not reusable_signal_saver.is_running

    def test_to_mark_allowed_double_stopping_for_simplicity(self, broker,
                                                            reusable_signal_saver, tmpdir):
        self._start_saving(broker, reusable_signal_saver, path=str(tmpdir))
        self._stop_saving(reusable_signal_saver)
        assert not reusable_signal_saver._session_is_active
        assert not reusable_signal_saver.is_running
        message = messages.StopSavingSignal()
        result = _run_synchronously(reusable_signal_saver, reusable_signal_saver._stop_saving_signal(message))
        assert type(result) == messages.SavingSignalStopped, result
        assert not reusable_signal_saver._session_is_active
        assert not reusable_signal_saver.is_running

    def test_saving_files_at_destination(self, broker, reusable_signal_saver, tmpdir):
        directory = '{}/manual/'.format(tmpdir)
        expected = {'{}/manual/default.xml'.format(tmpdir),
                    '{}/manual/default.tag'.format(tmpdir),
                    '{}/manual/default.raw'.format(tmpdir)}
        self._test_if_saves_files(broker, reusable_signal_saver, directory,
                                  prefix='', expected=expected)

    def test_saving_files_prefixes(self, broker, reusable_signal_saver, tmpdir):
        prefix = 'really'
        directory = '{}/not_used_path4'.format(tmpdir)
        expected = {'{}/not_used_path4/really.xml'.format(tmpdir),
                    '{}/not_used_path4/really.tag'.format(tmpdir),
                    '{}/not_used_path4/really.raw'.format(tmpdir)}
        self._test_if_saves_files(broker, reusable_signal_saver, directory,
                                  prefix=prefix, expected=expected)

    def test_saving_files_on_restarts(self, broker, reusable_signal_saver, tmpdir):
        directory = '{}/not_used_path2/'.format(tmpdir)
        expected = {'{}/not_used_path2/default.xml'.format(tmpdir),
                    '{}/not_used_path2/default.tag'.format(tmpdir),
                    '{}/not_used_path2/default.raw'.format(tmpdir)}
        self._test_if_saves_files(broker, reusable_signal_saver, directory,
                                  prefix='', expected=expected)
        self._test_if_saves_files(broker, reusable_signal_saver, directory,
                                  prefix='', expected=expected)
        directory = '{}/not_used_path3/'.format(tmpdir)
        expected = {'{}/not_used_path3/default.xml'.format(tmpdir),
                    '{}/not_used_path3/default.tag'.format(tmpdir),
                    '{}/not_used_path3/default.raw'.format(tmpdir)}
        self._test_if_saves_files(broker, reusable_signal_saver, directory,
                                  prefix='', expected=expected)

    def _test_if_saves_files(self, broker, reusable_signal_saver, directory,
                             prefix, expected):
        path = pathlib.Path(directory)
        assert not path.exists()
        try:
            self._start_saving(broker, reusable_signal_saver, path=directory,
                               files_prefix=prefix)
            self._stop_saving(reusable_signal_saver)
            assert path.exists()
            assert path.is_dir()
            assert expected == {str(path) for path in path.rglob('*')}
        except AssertionError:
            raise
        finally:
            for file in path.rglob('*'):
                file.unlink()
            path.rmdir()

    def test_restarting(self, broker, reusable_signal_saver, tmpdir):
        self._start_saving(broker, reusable_signal_saver, path=str(tmpdir))
        self._stop_saving(reusable_signal_saver)
        self._start_saving(broker, reusable_signal_saver, path=str(tmpdir))
        self._stop_saving(reusable_signal_saver)
        self._start_saving(broker, reusable_signal_saver, path=str(tmpdir))
        self._stop_saving(reusable_signal_saver)

    def test_saving_different_locations(self, broker, reusable_signal_saver, tmpdir):
        self._start_saving(broker, reusable_signal_saver, path='{}/brain_dump1/'.format(tmpdir),
                           files_prefix='one')
        assert reusable_signal_saver.get_param('save_file_path') == '{}/brain_dump1/'.format(tmpdir)
        assert reusable_signal_saver.get_param('save_file_name') == 'one'
        self._stop_saving(reusable_signal_saver)
        self._start_saving(broker, reusable_signal_saver, path='{}/brain_dump2/'.format(tmpdir),
                           files_prefix='two')
        assert reusable_signal_saver.get_param('save_file_path') == '{}/brain_dump2/'.format(tmpdir)
        assert reusable_signal_saver.get_param('save_file_name') == 'two'
        self._stop_saving(reusable_signal_saver)

    def _start_saving(self, broker, reusable_signal_saver,
                      path=None, files_prefix='',):
        assert path is not None
        utils.wait_until_peers_ready([broker, reusable_signal_saver], timeout=3)
        assert not reusable_signal_saver._session_is_active
        assert not reusable_signal_saver.is_running
        message = messages.StartSavingSignal(
            save_file_path=path,
            save_file_name=files_prefix,
        )
        result = _run_synchronously(reusable_signal_saver, reusable_signal_saver._start_saving_signal(message))
        assert type(result) == messages.SignalSavingStarted
        assert reusable_signal_saver._session_is_active
        assert reusable_signal_saver.is_running

    def _stop_saving(self, reusable_signal_saver):
        message = messages.StopSavingSignal()
        result = _run_synchronously(reusable_signal_saver, reusable_signal_saver._stop_saving_signal(message))
        assert type(result) == messages.SavingSignalStopped
        assert not reusable_signal_saver._session_is_active
        assert not reusable_signal_saver.is_running


def _run_synchronously(peer, coro):
    return asyncio.run_coroutine_threadsafe(coro, peer._loop).result()
