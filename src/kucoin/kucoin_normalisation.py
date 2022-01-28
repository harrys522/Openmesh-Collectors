from table import TableUtil

import json

class NormaliseKucoin():
    NO_EVENTS = {"lob_events": [], "market_orders": []}
    ACTIVE_LEVELS = set()
    QUOTE_NO = 2
    EVENT_NO = 0
    ORDER_ID = 0

    def __init__(self):
        self.util = TableUtil()

    def normalise(self, data) -> dict:
        """Jay"""
        lob_events = []
        market_orders = []

        # If the message is not a trade or a book update, ignore it. This can be seen by if the JSON response contains an "type" key.
        if data['type'] == 'ack' or data['type'] == 'welcome':
            print(f"Received message {json.dumps(data)}")
            return self.NO_EVENTS

        # Handling new LOB events
        if data['subject'] == "trade.l2update":
            order_data = data['data']['changes']
            for ask in order_data['asks']:
                price = float(ask[0])
                if price == 0:
                    return self.NO_EVENTS
                size = float(ask[1])
                ts = float(data['data']['sequenceStart'])
                # For Kucoin, if the order size is 0, it means that the level is being removed
                if size == 0:
                    lob_action = 3
                    if price in self.ACTIVE_LEVELS:
                        self.ACTIVE_LEVELS.remove(price)
                    self.QUOTE_NO += 1
                # If the price is already in the active levels, it means that the level is being updated with a new size
                elif price in self.ACTIVE_LEVELS:
                    lob_action = 4
                # Otherwise, it means that a new price level is being inserted
                else:
                    lob_action = 2
                    self.ACTIVE_LEVELS.add(price)
                # Once the nature of the lob event has been determined, it can be created and added to the list of lob events
                lob_events.append(self.util.create_lob_event(
                    quote_no=self.QUOTE_NO,
                    event_no=self.EVENT_NO,
                    order_id=self.ORDER_ID,
                    side=2,
                    price=price,
                    size=size if size else -1,
                    lob_action=lob_action,
                    receive_timestamp=data['receive_timestamp'],
                    order_type=0
                ))
                self.QUOTE_NO += 1
                self.ORDER_ID += 1
            for bid in order_data['bids']:
                price = float(bid[0])
                if price == 0:
                    return self.NO_EVENTS
                size = float(bid[1])
                if size == 0:
                    lob_action = 3
                    if price in self.ACTIVE_LEVELS:
                        self.ACTIVE_LEVELS.remove(price)
                    self.QUOTE_NO += 1
                elif price in self.ACTIVE_LEVELS:
                    lob_action = 4
                else:
                    lob_action = 2
                    self.ACTIVE_LEVELS.add(price)
                lob_events.append(self.util.create_lob_event(
                    quote_no=self.QUOTE_NO,
                    event_no=self.EVENT_NO,
                    order_id=self.ORDER_ID,
                    side=1,
                    price=price,
                    size=size if size else -1,
                    lob_action=lob_action,
                    receive_timestamp=data['receive_timestamp'],
                    order_type=0
                ))
                self.QUOTE_NO += 1
                self.ORDER_ID += 1

        elif data['subject'] == "trade.l3match":
            trade = data['data']
            market_orders.append(self.util.create_market_order(
                order_id=self.ORDER_ID,
                trade_id=trade['tradeId'],
                price=float(trade['price']),
                timestamp=float(trade['time']),
                side=1 if trade['side'] == 'buy' else 2,
                size=float(trade['size']),
            ))
            self.ORDER_ID += 1

        # If the data is in an unexpected format, ignore it
        else:
            print(f"Received unrecognised message {json.dumps(data)}")
            return self.NO_EVENTS
        self.EVENT_NO += 1

        # Creating final normalised data dictionary which will be returned to the Normaliser
        normalised = {
            "lob_events": lob_events,
            "market_orders": market_orders
        }

        return normalised