// static/socket.js
const socket = io();

// ========== ПОДКЛЮЧЕНИЕ ==========
socket.on('connect', () => {
    console.log('✅ Подключено к серверу');
    if (typeof USER_TOKEN !== 'undefined') {
        socket.emit('authenticate', { token: USER_TOKEN });
    }
});

socket.on('authenticated', (data) => {
    if (data.success) console.log('✅ Аутентификация успешна, user_id:', data.user_id);
});

// ========== СТАТУСЫ ==========
socket.on('user_status', (data) => {
    const contact = document.querySelector(`.contact[data-user-id="${data.user_id}"]`);
    if (contact) {
        const statusDot = contact.querySelector('.status');
        if (statusDot) statusDot.className = `status ${data.status}`;
    }
});

// ========== ОТПРАВКА СООБЩЕНИЙ ==========
window.sendMessage = (text, receiverId) => {
    socket.emit('send_message', { receiver_id: receiverId, text: text });
};

window.sendTyping = (isTyping) => {
    if (window.selectedReceiverId) {
        socket.emit('typing', { receiver_id: window.selectedReceiverId, is_typing: isTyping });
    }
};

socket.on('typing_indicator', (data) => {
    const typingStatus = document.getElementById('typing-status');
    if (typingStatus) {
        if (data.is_typing) {
            const contact = document.querySelector(`.contact[data-user-id="${data.user_id}"] .name`);
            const name = contact ? contact.textContent : 'Пользователь';
            typingStatus.textContent = `${name} печатает...`;
        } else {
            typingStatus.textContent = '';
        }
    }
});

// ========== ВСПОМОГАТЕЛЬНЫЕ ==========
function formatFileSize(bytes) {
    if (!bytes) return '';
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ========== ОТОБРАЖЕНИЕ СООБЩЕНИЙ ==========
window.addMessageToChat = function(data, type) {
    const container = document.getElementById('messages-container');
    if (!container) return;
    if (document.querySelector(`.message[data-message-id="${data.id}"]`)) return;
    
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${type}`;
    messageDiv.dataset.messageId = data.id;
    
    // Задача 3: Отображение даты в сообщениях
    const msgDate = new Date(data.sent_at);
    const now = new Date();
    const isToday = msgDate.toDateString() === now.toDateString();

    let time;
    if (isToday) {
        time = msgDate.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
    } else {
        time = msgDate.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
    }
    
    let contentHtml = '';
    
    if (data.file_path) {
        const fileUrl = data.file_path.startsWith('/') ? data.file_path : '/' + data.file_path;
        
        if (data.file_type === 'image') {
            contentHtml = `<div class="file-attachment"><img src="${fileUrl}" class="file-image" onclick="window.open(this.src)"><div class="file-name">${escapeHtml(fileUrl.split('/').pop())}</div></div>`;
        } else {
            contentHtml = `<div class="file-attachment"><a href="${fileUrl}" target="_blank" class="file-link">📎 ${escapeHtml(fileUrl.split('/').pop())}</a>${data.file_size ? `<div class="file-size">${formatFileSize(data.file_size)}</div>` : ''}</div>`;
        }
    }
    
    if (data.text && data.text.trim()) contentHtml += `<div class="message-text">${escapeHtml(data.text)}</div>`;
    if (!contentHtml) contentHtml = '<div class="message-text">Сообщение</div>';
    
    messageDiv.innerHTML = `
        <span class="sender">${escapeHtml(data.sender_name || 'Пользователь')}</span>
        ${contentHtml}
        <span class="time">${time}</span>
        ${type === 'sent' ? '<span class="message-status">✓</span>' : ''}
    `;
    
    container.appendChild(messageDiv);
    container.scrollTop = container.scrollHeight;
};

// ========== СОБЫТИЯ ==========
socket.on('message_sent', (data) => {
    window.addMessageToChat(data, 'sent');
    
    if (data.receiver_id) {
        fetch(`/api/last-message/${data.receiver_id}`)
            .then(r => r.json())
            .then(lastMsg => {
                if (window.updateContactLastMessage) {
                    window.updateContactLastMessage(data.receiver_id, lastMsg.last_message, lastMsg.last_time);
                }
            });
    }
});

socket.on('new_message', (data) => {
    window.addMessageToChat(data, 'received');
    socket.emit('message_delivered', { message_id: data.id });
    if (document.visibilityState === 'visible') {
        socket.emit('message_read', { message_id: data.id });
    }
    
    if (data.sender_id) {
        fetch(`/api/last-message/${data.sender_id}`)
            .then(r => r.json())
            .then(lastMsg => {
                if (window.updateContactLastMessage) {
                    window.updateContactLastMessage(data.sender_id, lastMsg.last_message, lastMsg.last_time);
                }
                if (window.updateUnreadCount && lastMsg.unread_count !== undefined) {
                    window.updateUnreadCount(data.sender_id, lastMsg.unread_count);
                }
            });
    }
});

socket.on('message_edited', (data) => {
    const msgEl = document.querySelector(`.message[data-message-id="${data.message_id}"]`);
    if (msgEl) {
        const textDiv = msgEl.querySelector('.message-text');
        if (textDiv) textDiv.innerHTML = escapeHtml(data.new_text);
        let editedSpan = msgEl.querySelector('.edited-indicator');
        if (!editedSpan) {
            editedSpan = document.createElement('span');
            editedSpan.className = 'edited-indicator';
            editedSpan.textContent = ' (ред.)';
            const timeEl = msgEl.querySelector('.time');
            if (timeEl) timeEl.after(editedSpan);
        }
    }
});

socket.on('message_deleted', (data) => {
    document.querySelector(`.message[data-message-id="${data.message_id}"]`)?.remove();
});

socket.on('message_status_update', (data) => {
    const msgEl = document.querySelector(`.message[data-message-id="${data.message_id}"]`);
    if (!msgEl) return;
    if (msgEl.classList.contains('sent')) {
        let statusEl = msgEl.querySelector('.message-status');
        if (!statusEl) {
            statusEl = document.createElement('span');
            statusEl.className = 'message-status';
            const timeEl = msgEl.querySelector('.time');
            if (timeEl) timeEl.after(statusEl);
        }
        if (data.status === 'delivered') {
            statusEl.textContent = '✓✓';
            statusEl.style.color = '';
        } else if (data.status === 'read') {
            statusEl.textContent = '✓✓';
            statusEl.style.color = '#4fc3f7';
        }
    }
});

// ========== ЭКСПОРТ ==========
window.exportChat = function(chatName, messages) {
    let content = `Экспорт чата с ${chatName}\nДата: ${new Date().toLocaleString()}\n${'='.repeat(50)}\n\n`;
    messages.forEach(msg => {
        const date = new Date(msg.sent_at).toLocaleString();
        const sender = msg.sender_id === USER_ID ? 'Я' : msg.sender_name;
        content += `[${date}] ${sender}: ${msg.text || 'Файл'}\n`;
        if (msg.file_path) content += `  [Файл: ${msg.file_path.split('/').pop()}]\n`;
    });
    const blob = new Blob([content], { type: 'text/plain' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `chat_${chatName}_${Date.now()}.txt`;
    link.click();
    URL.revokeObjectURL(link.href);
};