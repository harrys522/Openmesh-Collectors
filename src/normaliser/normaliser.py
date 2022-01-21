"""
normaliser

Mediator class which provides a wrapper for normalising data from a websocket feed.
Instantiates the correct websocket connection with an ID.
"""
from threading import Thread, Lock
from time import sleep
import os

from .manager.ws_factories import FactoryRegistry
from .normalising_strategies import NormalisingStrategies
from .tables.table import LobTable, MarketOrdersTable
from .jit_order_book import OrderBookManager
from .metrics import Metric


class Normaliser():
    def __init__(self, exchange_id: str, symbol: str, name = None):
        self.name = name
        # Initialise WebSocket handler
        self.ws_manager = FactoryRegistry().get_ws_manager(exchange_id, symbol)

        # Retrieve correct normalisation function
        self.normalise = NormalisingStrategies().get_strategy(exchange_id)

        # Initialise tables
        self.lob_table = LobTable()
        self.market_orders_table = MarketOrdersTable()
        self.order_book_manager = OrderBookManager()

        # Metric observers
        self.metrics = []

        # Initialise locks
        self.lob_table_lock = Lock()
        self.metric_lock = Lock()
        self.lob_lock = Lock()

        # Start normalising the data
        self.normalise_thr = Thread(
            name="normalising_thread",
            target=self._normalise_thread,
            args=(),
            daemon=True
        )
        self.normalise_thr.start()
        sleep(1)

    def put_entry(self, data: dict):
        """
        Puts data into the table.

        If you've implemented your normalisation algorithm correctly, it should automatically put your 
        data into the correct table.
        """
        data = self.normalise(data)
        lob_events = data["lob_events"]
        market_orders = data["market_orders"]

        self.lob_table_lock.acquire()
        self.lob_lock.acquire()
        for event in lob_events:
            if len(event) == 22:
                self.lob_table.put_dict(event)
                self.order_book_manager.handle_event(event)
        self.lob_lock.release()
        self.lob_table_lock.release()

        for order in market_orders:
            if len(order) == 6:
                self.market_orders_table.put_dict(order)

        self.calculate_metrics()



    def get_lob_events(self):
        # NOTE: MODIFYING THE LOB TABLE AFTER RETRIEVING IT USING THIS FUNCTION IS NOT THREAD SAFE
        #       It is only safe for metric which are observing this normaliser through the calculate_metrics method.
        return self.lob_table

    def get_best_orders(self):
        return self.order_book_manager.best_buy_order, self.order_book_manager.best_sell_order

    def get_market_orders(self):
        return self.market_orders_table

    def dump(self):
        #os.system("clear")
        if self.name:
            print(f"-------------------------------------------------START {self.name}-------------------------------------------------")
        """
        print("LOB Events")
        self.lob_table_lock.acquire()
        self.lob_table.dump()
        self.lob_table_lock.release()
        """

        """
        print("Market Orders")
        self.market_orders_table.dump()
        """

        self.lob_lock.acquire()
        self.order_book_manager.dump()
        self.lob_lock.release()

        """
        # Queue backlog
        self.ws_manager.get_q_size()
        """

        
        print("-------------------------METRICS---------------------------")
        self.metric_lock.acquire()
        for metric in self.metrics:
            metric.display_metric()
        self.metric_lock.release()
        print("-----------------------------------------------------------")
        
        if self.name:
            print(f"--------------------------------------------------END {self.name}--------------------------------------------------")
    
    def add_metric(self, metric: Metric):
        if metric in self.metrics:
            return
        self.metrics.append(metric)

    def remove_metric(self, metric: Metric):
        if not metric in self.metrics:
            return
        self.metrics.remove(metric)

    def calculate_metrics(self):
        threads = []
        self.lob_table_lock.acquire()
        self.lob_lock.acquire()
        self.metric_lock.acquire()
        for metric in self.metrics:
            t = Thread(
                target=Metric.metric_wrapper,
                args=(metric.calculate, self),
                daemon=True
            )
            threads.append(t)
            t.start()
        for thread in threads:
            t.join()
        """
        for metric in self.metrics:
            Metric.metric_wrapper(metric.calculate, self)
        """
        self.metric_lock.release()
        self.lob_lock.release()
        self.lob_table_lock.release()

    def _normalise_thread(self):
        while True:
            # NOTE: This function blocks when there are no messages in the queue.
            data = self.ws_manager.get_msg()
            self.put_entry(data)
