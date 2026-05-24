from flask import Flask, render_template, request, redirect, session, url_for, jsonify, send_from_directory
from flask_socketio import SocketIO, emit
from database import Database
from auth import create_access_token, verify_token
import secrets
from datetime import datetime
import os
import mimetypes
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

# Настройки загрузки
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'txt', 'pdf', 'doc', 'docx', 'zip', 'mp3', 'mp4', 'webm', 'wav', 'ogg', 'm4a'}
MAX_FILE_SIZE = 10 * 1024 * 1024

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

socketio = SocketIO(app, cors_allowed_origins="*")
db = Database("messenger.db")
user_sockets = {}

# ========== HTTP МАРШРУТЫ ==========

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('chat'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        login = request.form.get('login')
        password = request.form.get('password')
        
        if not login or not password:
            return render_template('login.html', error="Заполните все поля")
        
        user = db.verify_user(login, password)
        
        if user:
            token = create_access_token(data={"sub": str(user['id'])})
            session['user_id'] = user['id']
            session['user_name'] = user['display_name']
            return render_template('chat.html', user_name=user['display_name'], token=token)
        else:
            return render_template('login.html', error="Неверный логин или пароль")
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        login = request.form.get('login')
        password = request.form.get('password')
        confirm = request.form.get('confirm')
        name = request.form.get('name', login)
        
        if not login or not password:
            return render_template('register.html', error="Заполните все поля")
        
        if password != confirm:
            return render_template('register.html', error="Пароли не совпадают")
        
        existing = db.get_user_by_login(login)
        if existing:
            return render_template('register.html', error="Пользователь уже существует")
        
        try:
            db.add_user(login, password, name)
            return redirect(url_for('login'))
        except Exception as e:
            return render_template('register.html', error=f"Ошибка: {e}")
    
    return render_template('register.html')

@app.route('/chat')
def chat():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    token = create_access_token(data={"sub": str(session['user_id'])})
    return render_template('chat.html', user_name=session['user_name'], token=token)

@app.route('/logout')
def logout():
    user_id = session.get('user_id')
    if user_id and user_id in user_sockets:
        del user_sockets[user_id]
        db.update_user_status(user_id, 'offline')
        emit('user_status', {'user_id': user_id, 'status': 'offline'}, broadcast=True)
    
    session.clear()
    return redirect(url_for('login'))

# ========== API ==========

@app.route('/api/users')
def get_users():
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id, display_name FROM users ORDER BY display_name')
        users = [dict(row) for row in cursor.fetchall()]
    
    return jsonify({'users': users})

@app.route('/api/messages/with/<int:other_user_id>')
def get_messages_with_user(other_user_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    user_id = session['user_id']
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)
    
    messages = db.get_messages_between_users(user_id, other_user_id, limit, offset)
    total = db.get_total_messages_count(user_id, other_user_id)
    
    return jsonify({'messages': messages, 'total': total, 'has_more': offset + limit < total})

@app.route('/api/messages/search/<int:other_user_id>')
def search_messages_with_user(other_user_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    query = request.args.get('q', '')
    if not query or len(query) < 2:
        return jsonify({'messages': []})
    
    user_id = session['user_id']
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)
    
    messages = db.search_messages_in_chat(user_id, other_user_id, query, limit, offset)
    return jsonify({'messages': messages, 'query': query})

@app.route('/api/last-message/<int:other_user_id>')
def get_last_message(other_user_id):
    """Возвращает последнее сообщение и количество непрочитанных для контакта"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    user_id = session['user_id']
    
    with db._get_connection() as conn:
        cursor = conn.cursor()
        
        # Находим чат между пользователями
        cursor.execute('''
            SELECT c.id FROM chats c
            JOIN chat_participants cp1 ON c.id = cp1.chat_id
            JOIN chat_participants cp2 ON c.id = cp2.chat_id
            WHERE c.type = 'dialog'
              AND cp1.user_id = ?
              AND cp2.user_id = ?
        ''', (user_id, other_user_id))
        
        chat_row = cursor.fetchone()
        if not chat_row:
            return jsonify({'last_message': None, 'last_time': None, 'unread_count': 0})
        
        chat_id = chat_row['id']
        
        # Последнее сообщение в чате
        cursor.execute('''
            SELECT text, sent_at FROM messages 
            WHERE chat_id = ? 
            ORDER BY sent_at DESC LIMIT 1
        ''', (chat_id,))
        last_msg = cursor.fetchone()
        
        # Количество непрочитанных сообщений от этого пользователя
        cursor.execute('''
            SELECT COUNT(*) as count FROM messages 
            WHERE chat_id = ? AND sender_id = ? AND (read_at IS NULL OR status != 'read')
        ''', (chat_id, other_user_id))
        unread = cursor.fetchone()
        
        return jsonify({
            'last_message': last_msg['text'] if last_msg else None,
            'last_time': last_msg['sent_at'] if last_msg else None,
            'unread_count': unread['count'] if unread else 0
        })

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    """Отдача файлов с правильным MIME-типом"""
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    if ext in ['mp3', 'wav', 'ogg', 'webm', 'm4a', 'flac']:
        mimetypes.add_type('audio/' + ext, '.' + ext)
    
    return send_from_directory(UPLOAD_FOLDER, filename)

@app.route('/api/upload', methods=['POST'])
def upload_file():
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    if 'file' not in request.files:
        return jsonify({'error': 'No file'}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': 'File type not allowed'}), 400
    
    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)
    
    if file_size > MAX_FILE_SIZE:
        return jsonify({'error': f'File too large (max 10MB)'}), 400
    
    filename = secure_filename(f"{datetime.now().timestamp()}_{file.filename}")
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    
    ext = filename.rsplit('.', 1)[1].lower()
    if ext in ['png', 'jpg', 'jpeg', 'gif', 'webp']:
        file_type = 'image'
    elif ext in ['mp3', 'wav', 'ogg', 'webm', 'm4a', 'aac', 'flac']:
        file_type = 'audio'
    elif ext in ['mp4', 'avi', 'mov', 'mkv']:
        file_type = 'video'
    else:
        file_type = 'file'
    
    return jsonify({
        'success': True,
        'file_path': f'/uploads/{filename}',
        'file_size': file_size,
        'filename': filename,
        'file_type': file_type
    })

# ========== WEBSOCKET ==========

@socketio.on('connect')
def handle_connect():
    print(f"🔌 Клиент подключился: {request.sid}")

@socketio.on('disconnect')
def handle_disconnect():
    for user_id, sid in list(user_sockets.items()):
        if sid == request.sid:
            del user_sockets[user_id]
            db.update_user_status(user_id, 'offline')
            emit('user_status', {'user_id': user_id, 'status': 'offline'}, broadcast=True)
            break

@socketio.on('authenticate')
def handle_authenticate(data):
    token = data.get('token')
    user_id = verify_token(token)
    
    if user_id:
        user_sockets[int(user_id)] = request.sid
        emit('authenticated', {'success': True, 'user_id': user_id})
        db.update_user_status(int(user_id), 'online')
        emit('user_status', {'user_id': int(user_id), 'status': 'online'}, broadcast=True)

@socketio.on('send_message')
def handle_send_message(data):
    sender_id = None
    for uid, sid in user_sockets.items():
        if sid == request.sid:
            sender_id = uid
            break
    
    if not sender_id:
        return
    
    receiver_id = data.get('receiver_id')
    text = data.get('text', '').strip()
    
    if not receiver_id or not text:
        return
    
    sender = db.get_user(sender_id)
    sender_name = sender['display_name'] if sender else 'Unknown'
    
    chat_id = db.get_or_create_dialog(sender_id, receiver_id)
    message_id = db.create_message(sender_id, chat_id, text)
    
    message_data = {
        'id': message_id,
        'sender_id': sender_id,
        'sender_name': sender_name,
        'receiver_id': receiver_id,
        'chat_id': chat_id,
        'text': text,
        'sent_at': datetime.now().isoformat(),
        'status': 'sent'
    }
    
    emit('message_sent', message_data, room=request.sid)
    
    if receiver_id in user_sockets:
        emit('new_message', message_data, room=user_sockets[receiver_id])

@socketio.on('send_file')
def handle_send_file(data):
    print(f"📨 send_file получен: {data}")
    
    sender_id = None
    for uid, sid in user_sockets.items():
        if sid == request.sid:
            sender_id = uid
            break
    
    if not sender_id:
        return
    
    receiver_id = data.get('receiver_id')
    file_path = data.get('file_path')
    file_size = data.get('file_size')
    file_type = data.get('file_type', 'file')
    
    if not receiver_id or not file_path:
        return
    
    sender = db.get_user(sender_id)
    sender_name = sender['display_name'] if sender else 'Unknown'
    
    chat_id = db.get_or_create_dialog(sender_id, receiver_id)
    message_id = db.create_message_with_file(sender_id, chat_id, "", file_path, file_size, file_type)
    
    message_data = {
        'id': message_id,
        'sender_id': sender_id,
        'sender_name': sender_name,
        'receiver_id': receiver_id,
        'chat_id': chat_id,
        'text': '',
        'file_path': file_path,
        'file_size': file_size,
        'file_type': file_type,
        'sent_at': datetime.now().isoformat(),
        'status': 'sent'
    }
    
    emit('message_sent', message_data, room=request.sid)
    
    if receiver_id in user_sockets:
        emit('new_message', message_data, room=user_sockets[receiver_id])

@socketio.on('edit_message')
def handle_edit_message(data):
    message_id = data.get('message_id')
    new_text = data.get('text', '').strip()
    
    if not message_id or not new_text:
        return
    
    user_id = None
    for uid, sid in user_sockets.items():
        if sid == request.sid:
            user_id = uid
            break
    
    if not user_id:
        return
    
    message = db.get_message(message_id)
    if not message or message['sender_id'] != user_id:
        return
    
    db.update_message(message_id, new_text)
    emit('message_edited', {'message_id': message_id, 'new_text': new_text}, broadcast=True)

@socketio.on('delete_message')
def handle_delete_message(data):
    message_id = data.get('message_id')
    
    user_id = None
    for uid, sid in user_sockets.items():
        if sid == request.sid:
            user_id = uid
            break
    
    if not user_id or not message_id:
        return
    
    if db.delete_message(message_id, user_id):
        emit('message_deleted', {'message_id': message_id}, broadcast=True)

@socketio.on('message_delivered')
def handle_message_delivered(data):
    message_id = data.get('message_id')
    if message_id:
        db.mark_message_delivered(message_id)
        emit('message_status_update', {'message_id': message_id, 'status': 'delivered'}, broadcast=True)

@socketio.on('message_read')
def handle_message_read(data):
    message_id = data.get('message_id')
    
    user_id = None
    for uid, sid in user_sockets.items():
        if sid == request.sid:
            user_id = uid
            break
    
    if message_id and user_id:
        db.mark_message_read(message_id, user_id)
        emit('message_status_update', {'message_id': message_id, 'status': 'read'}, broadcast=True)

@socketio.on('typing')
def handle_typing(data):
    sender_id = None
    for uid, sid in user_sockets.items():
        if sid == request.sid:
            sender_id = uid
            break
    
    if not sender_id:
        return
    
    receiver_id = data.get('receiver_id')
    is_typing = data.get('is_typing', False)
    
    if receiver_id and receiver_id in user_sockets:
        emit('typing_indicator', {'user_id': sender_id, 'is_typing': is_typing}, room=user_sockets[receiver_id])

@socketio.on('add_reaction')
def handle_add_reaction(data):
    message_id = data.get('message_id')
    reaction = data.get('reaction')
    
    user_id = None
    for uid, sid in user_sockets.items():
        if sid == request.sid:
            user_id = uid
            break
    
    if message_id and reaction and user_id:
        db.add_reaction(message_id, user_id, reaction)
        emit('reaction_updated', {
            'message_id': message_id,
            'reaction': reaction,
            'user_id': user_id,
            'action': 'add'
        }, broadcast=True)

@socketio.on('remove_reaction')
def handle_remove_reaction(data):
    message_id = data.get('message_id')
    
    user_id = None
    for uid, sid in user_sockets.items():
        if sid == request.sid:
            user_id = uid
            break
    
    if message_id and user_id:
        db.remove_reaction(message_id, user_id)
        emit('reaction_updated', {
            'message_id': message_id,
            'user_id': user_id,
            'action': 'remove'
        }, broadcast=True)

# ========== ЗАПУСК ==========

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)