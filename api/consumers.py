import json
from channels.generic.websocket import AsyncWebsocketConsumer


class SeatStatusConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer that manages real-time seat availability updates.

    Each showtime has its own channel group: "showtime_{id}_seats".
    When any client books or locks a seat, the server broadcasts to the
    group and every connected browser updates that seat's color instantly —
    no polling required.

    Connection lifecycle:
        connect()    -> join the showtime's channel group
        receive()    -> clients are read-only; no inbound messages expected
        disconnect() -> leave the group, free the channel slot
        seat_status_update() -> handler called when group_send is triggered
    """

    async def connect(self):
        self.showtime_id = self.scope['url_route']['kwargs']['showtime_id']
        self.group_name  = f'showtime_{self.showtime_id}_seats'

        # Register this WebSocket connection in the channel group
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        # Clients are read-only — seat updates flow server → client only
        pass

    # ----- Group message handler -----
    # Called when views.py sends a group_send with type='seat_status_update'
    async def seat_status_update(self, event):
        """Push a seat status change to this specific WebSocket client."""
        await self.send(text_data=json.dumps({
            'type':        'seat_update',
            'seat_id':     event['seat_id'],
            'seat_number': event['seat_number'],
            'status':      event['status'],   # AVAILABLE | LOCKED | BOOKED
        }))
