from channels.generic.websocket import WebsocketConsumer
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from asgiref.sync import async_to_sync
import json
from .models import *

class ChatroomConsumer(WebsocketConsumer):
    # Method called when a new WebSocket connection is established
    def connect(self):
        self.user = self.scope['user']
        self.chatroom_name = self.scope['url_route']['kwargs']['chatroom_name'] 
        self.chatroom = get_object_or_404(ChatGroup, group_name=self.chatroom_name)
        
        # Add the channel to the WebSocket group
        async_to_sync(self.channel_layer.group_add)(
            self.chatroom_name, self.channel_name
        )
        
        # Add user to online users list if not already present
        if self.user not in self.chatroom.users_online.all():
            self.chatroom.users_online.add(self.user)
            self.update_online_count()
        
        self.accept()
        
    # Method called when the WebSocket connection is closed
    def disconnect(self, close_code):
        # Remove the channel from the WebSocket group
        async_to_sync(self.channel_layer.group_discard)(
            self.chatroom_name, self.channel_name
        )
        
        # Remove user from online users list and update count
        if self.user in self.chatroom.users_online.all():
            self.chatroom.users_online.remove(self.user)
            self.update_online_count() 
        
    # Method called when a message is received from the WebSocket
    def receive(self, text_data):
        text_data_json = json.loads(text_data)
        body = text_data_json['body']
        
        # Save the received message in the database
        message = GroupMessage.objects.create(
            body = body,
            author = self.user, 
            group = self.chatroom 
        )
        
        # Send the new message event to the WebSocket group
        event = {
            'type': 'message_handler',
            'message_id': message.id,
        }
        async_to_sync(self.channel_layer.group_send)(
            self.chatroom_name, event
        )
        
    # Method to handle message events and send them to the WebSocket
    def message_handler(self, event):
        message_id = event['message_id']
        message = GroupMessage.objects.get(id=message_id)
        
        # Render the message using a template
        context = {
            'message': message,
            'user': self.user,
            'chat_group': self.chatroom
        }
        html = render_to_string("a_rtchat/partials/chat_message_p.html", context=context)
        
        # Send the rendered message to the WebSocket
        self.send(text_data=html)
        
    # Method to update the online user count for the chatroom
    def update_online_count(self):
        online_count = self.chatroom.users_online.count() - 1
        
        # Send online count update event to the WebSocket group
        event = {
            'type': 'online_count_handler',
            'online_count': online_count
        }
        async_to_sync(self.channel_layer.group_send)(self.chatroom_name, event)
        
    # Method to handle online count update events and send them to the WebSocket
    def online_count_handler(self, event):
        online_count = event['online_count']
        
        # Fetch last 30 chat messages and their authors
        chat_messages = ChatGroup.objects.get(group_name=self.chatroom_name).chat_messages.all()[:30]
        author_ids = set([message.author.id for message in chat_messages])
        users = User.objects.filter(id__in=author_ids)
        
        # Render the online user count using a template
        context = {
            'online_count' : online_count,
            'chat_group' : self.chatroom,
            'users': users
        }
        html = render_to_string("a_rtchat/partials/online_count.html", context)
        
        # Send the rendered online count to the WebSocket
        self.send(text_data=html) 
        

class OnlineStatusConsumer(WebsocketConsumer):
    # Method called when a new WebSocket connection is established
    def connect(self):
        self.user = self.scope['user']
        self.group_name = 'online-status'
        self.group = get_object_or_404(ChatGroup, group_name=self.group_name)
        
        # Add user to online users list if not already present
        if self.user not in self.group.users_online.all():
            self.group.users_online.add(self.user)
            
        # Add the channel to the WebSocket group
        async_to_sync(self.channel_layer.group_add)(
            self.group_name, self.channel_name
        )
        
        self.accept()
        self.online_status()
        
    # Method called when the WebSocket connection is closed
    def disconnect(self, close_code):
        # Remove user from online users list
        if self.user in self.group.users_online.all():
            self.group.users_online.remove(self.user)
            
        # Remove the channel from the WebSocket group
        async_to_sync(self.channel_layer.group_discard)(
            self.group_name, self.channel_name
        )
        self.online_status()
        
    # Method to notify the group about online status updates
    def online_status(self):
        event = {
            'type': 'online_status_handler'
        }
        async_to_sync(self.channel_layer.group_send)(
            self.group_name, event
        ) 
        
    # Method to handle online status updates and send them to the WebSocket
    def online_status_handler(self, event):
        online_users = self.group.users_online.exclude(id=self.user.id)
        public_chat_users = ChatGroup.objects.get(group_name='public-chat').users_online.exclude(id=self.user.id)
        
        # Fetch private and group chats where other users are online
        my_chats = self.user.chat_groups.all()
        private_chats_with_users = [chat for chat in my_chats.filter(is_private=True) if chat.users_online.exclude(id=self.user.id)]
        group_chats_with_users = [chat for chat in my_chats.filter(groupchat_name__isnull=False) if chat.users_online.exclude(id=self.user.id)]
        
        # Determine if any chats have active users
        if public_chat_users or private_chats_with_users or group_chats_with_users:
            online_in_chats = True
        else:
            online_in_chats = False
        
        # Render the online status using a template
        context = {
            'online_users': online_users,
            'online_in_chats': online_in_chats,
            'public_chat_users': public_chat_users,
            'user': self.user
        }
        html = render_to_string("a_rtchat/partials/online_status.html", context=context)
        
        # Send the rendered online status to the WebSocket
        self.send(text_data=html)
