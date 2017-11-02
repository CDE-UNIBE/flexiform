from formtools.wizard.storage.session import SessionStorage


class NoSession(SessionStorage):
    def _set_data(self, value):
        pass
