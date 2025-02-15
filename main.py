from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.lang import Builder
from kivy.core.window import Window
from kivy.clock import Clock

# Define the KV language string for styling
Builder.load_string('''
<ChatInterface>:
    orientation: 'horizontal'
    canvas.before:
        Color:
            rgba: 0.15, 0.15, 0.15, 1
        Rectangle:
            pos: self.pos
            size: self.size
    
    # Sidebar
    BoxLayout:
        orientation: 'vertical'
        size_hint_x: 0.2
        padding: [15, 10]
        spacing: 15
        canvas.before:
            Color:
                rgba: 0.2, 0.2, 0.2, 1
            RoundedRectangle:
                pos: self.pos
                size: self.size
                radius: [0, 15, 15, 0]
        
        Button:
            id: new_chat_btn
            text: '+ New chat'
            size_hint_y: None
            height: 45
            background_color: 0, 0, 0, 0
            color: 0.9, 0.9, 0.9, 1
            font_size: '15sp'
            canvas.before:
                Color:
                    rgba: 0.25, 0.25, 0.25, 1
                RoundedRectangle:
                    pos: self.pos
                    size: self.size
                    radius: [15]
        
        Button:
            id: clear_history_btn
            text: 'Clear History'
            size_hint_y: None
            height: 45
            background_color: 0, 0, 0, 0
            color: 0.9, 0.9, 0.9, 1
            font_size: '15sp'
            canvas.before:
                Color:
                    rgba: 0.25, 0.25, 0.25, 1
                RoundedRectangle:
                    pos: self.pos
                    size: self.size
                    radius: [15]
    
    # Main chat area
    BoxLayout:
        orientation: 'vertical'
        padding: [20, 10]
        spacing: 20
        
        ScrollView:
            BoxLayout:
                id: chat_messages
                orientation: 'vertical'
                size_hint_y: None
                height: self.minimum_height
                spacing: 20
                padding: [0, 20]
        
        # Input area
        BoxLayout:
            size_hint_y: None
            height: 80
            padding: [50, 10]
            spacing: 10
            
            BoxLayout:
                canvas.before:
                    Color:
                        rgba: 0.25, 0.25, 0.25, 1
                    RoundedRectangle:
                        pos: self.pos
                        size: self.size
                        radius: [15]
                padding: [15, 10]
                
                TextInput:
                    id: message_input
                    hint_text: 'Send a message'
                    multiline: True
                    background_color: 0, 0, 0, 0
                    cursor_color: 1, 1, 1, 1
                    foreground_color: 1, 1, 1, 1
                    font_size: '16sp'
                    hint_text_color: 0.5, 0.5, 0.5, 1
                    padding: [10, 10]
            
            Button:
                id: send_button
                size_hint: None, None
                size: 60, 60
                text: 'Send'
                background_color: 0, 0, 0, 0
                color: 1, 1, 1, 1
                canvas.before:
                    Color:
                        rgba: 0.3, 0.3, 0.3, 1 if self.state == 'normal' else (0.4, 0.4, 0.4, 1)
                    RoundedRectangle:
                        pos: self.pos
                        size: self.size
                        radius: [15]
''')

class ChatInterface(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        Window.clearcolor = (0.1, 0.1, 0.1, 1)
        # Bind buttons
        self.ids.send_button.bind(on_press=lambda x: self.handle_send())
        self.ids.message_input.bind(on_text_validate=lambda x: self.handle_send())
        self.ids.new_chat_btn.bind(on_release=self.new_chat)
        self.ids.clear_history_btn.bind(on_release=self.clear_history)
        
        # Bind keyboard
        Window.bind(on_key_down=self.on_key_down)

    def on_key_down(self, instance, keyboard, keycode, text, modifiers):
        # Check if the focused widget is the message input and Enter key is pressed
        if self.ids.message_input.focus and keycode == 40:  # 40 is the keycode for Enter
            if 'shift' not in modifiers:  # If shift is not pressed
                self.handle_send()
                return True
        return False

    def handle_send(self, *args):
        message = self.ids.message_input.text.strip()
        if message:
            # Create user message bubble
            user_message = Label(
                text=message,
                size_hint_y=None,
                height=60,
                text_size=(self.width * 0.7, None),
                halign='right',
                color=(1, 1, 1, 1),
                padding=(10, 10)
            )
            
            # Add message to chat
            self.ids.chat_messages.add_widget(user_message)
            
            # Clear input
            self.ids.message_input.text = ''
            
            # Simulate AI response
            ai_response = Label(
                text=f"You said: {message}",
                size_hint_y=None,
                height=60,
                text_size=(self.width * 0.7, None),
                halign='left',
                color=(1, 1, 1, 1),
                padding=(10, 10)
            )
            self.ids.chat_messages.add_widget(ai_response)
            
            # Scroll to bottom
            Clock.schedule_once(lambda dt: self.scroll_to_bottom())

    def scroll_to_bottom(self):
        scroll_view = self.ids.chat_messages.parent
        scroll_view.scroll_y = 0

    def new_chat(self, instance):
        # Clear the chat messages
        self.ids.chat_messages.clear_widgets()
        # Clear the input field
        self.ids.message_input.text = ''
        # Add a welcome message
        welcome_msg = Label(
            text="Start a new conversation!",
            size_hint_y=None,
            height=40,
            color=(0.7, 0.7, 0.7, 1),
            font_size='16sp'
        )
        self.ids.chat_messages.add_widget(welcome_msg)

    def clear_history(self, instance):
        # Clear all messages
        self.ids.chat_messages.clear_widgets()
        # Clear the input field
        self.ids.message_input.text = ''

class ChatGPTCloneApp(App):
    def build(self):
        return ChatInterface()

if __name__ == '__main__':
    ChatGPTCloneApp().run()
