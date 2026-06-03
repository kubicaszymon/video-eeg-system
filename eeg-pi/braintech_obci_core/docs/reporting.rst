Reporting
=========
To report errors in BCI Framework we use redmine & sentry. In addition there are some tools & places in BCI Framework which are
responsible for this.

Tools
-----
1. ``obci report_error`` command.

Any time you want to send report to sentry with latest experiment logs (experiment must be closed, because logs are
fetched from main database to which logs from experiments are merged after closing) you should type it. It'll expose a
window with title and description forms for problem you have stumbled upon.

In addition you can configure your redmine client in ``~/.obci/main_config.ini`` file by filling ``url`` and
``token`` in
``redmine`` section with our redmine url and your private redmine API token (you can find it at
``$redmine_url/my/account``). After that additional section ``parent_id`` should be present in the form. You can fill it
to create a task binded to a given issue number (``parent_id``) or leave it empty in which case it'll create a ``bug``
issue in redmine.

To make sentry issue url appear in redmine description you must also supply ``sentry_token`` in ``server`` section in
your ``main_config.ini``. You can find this token here: https://sentry.io/api/
