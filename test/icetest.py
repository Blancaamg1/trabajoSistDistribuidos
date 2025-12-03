import logging
import time
from functools import cached_property
from threading import Thread
from unittest import TestCase

import Ice


class IceTestCase(TestCase):
    def ice_initialize_with_props(self, props_dict):
        init_data = Ice.InitializationData()
        init_data.properties = Ice.createProperties()
        for k, v in props_dict.items():
            init_data.properties.setProperty(k, v)

        return Ice.initialize(init_data)

    def wait_object_ready(self, proxy):
        attempts = 3
        proxy = proxy.ice_timeout(500)
        for _ in range(attempts):
            try:
                proxy.ice_ping()
                return
            except Ice.Exception:
                time.sleep(0.5)

        self.fail(f'Object not ready after {attempts} attempts')

    @cached_property
    def client_ic(self):
        client_ic = Ice.initialize()
        self.addCleanup(client_ic.destroy)
        return client_ic

    def create_proxy(self, proxy_str, cast):
        proxy = self.client_ic.stringToProxy(proxy_str)
        self.wait_object_ready(proxy)
        proxy = cast.checkedCast(proxy)
        self.assertIsNotNone(proxy)
        return proxy

    def create_server(self, main, props, *args):
        ic = self.ice_initialize_with_props(props)
        args = (ic,) + args
        thread = Thread(target=main, args=args)
        thread.start()
        self.addCleanup(self.server_shutdown, ic, thread)

    @staticmethod
    def server_shutdown(ic, thread):
        ic.shutdown()
        ic.destroy()

        thread.join(3)
        if thread.is_alive():
            logging.warning("Thread could not be joined in time")
