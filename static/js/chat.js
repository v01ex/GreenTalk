// Функция для отметки всех сообщений как прочитанные
function markAllMessagesAsRead() {
    const unreadMessages = document.querySelectorAll('.message.unread');
    
    if (unreadMessages.length === 0) return;
    
    unreadMessages.forEach(message => {
        message.classList.remove('unread');
        message.querySelector('.unread-indicator')?.remove();
    });
    
    // Обновить счетчик непрочитанных
    document.querySelector('.unread-count').textContent = '0';
    document.querySelector('.unread-count').style.display = 'none';
    
    // Отправить запрос на сервер
    fetch('/mark_all_read', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCookie('csrftoken')
        },
        body: JSON.stringify({
            chat_id: currentChatId
        })
    })
    .catch(error => {
        console.error('Ошибка при отметке сообщений как прочитанных:', error);
    });
}

// Инициализация кнопки "Отметить все как прочитанное"
function initMarkAllReadButton() {
    const markAllReadBtn = document.createElement('div');
    markAllReadBtn.className = 'mark-all-read-btn';
    markAllReadBtn.innerHTML = '<i class="fas fa-check-double"></i>Отметить все как прочитанное';
    markAllReadBtn.addEventListener('click', markAllMessagesAsRead);
    
    // Вставить кнопку перед блоком сообщений
    const messagesContainer = document.querySelector('.messages-container');
    messagesContainer.parentNode.insertBefore(markAllReadBtn, messagesContainer);
    
    // Показывать кнопку только если есть непрочитанные сообщения
    updateMarkAllReadButtonVisibility();
}

// Обновить видимость кнопки "Отметить все как прочитанное"
function updateMarkAllReadButtonVisibility() {
    const markAllReadBtn = document.querySelector('.mark-all-read-btn');
    if (!markAllReadBtn) return;
    
    const unreadMessages = document.querySelectorAll('.message.unread').length;
    markAllReadBtn.style.display = unreadMessages > 0 ? 'flex' : 'none';
}

// Вызываем инициализацию при загрузке документа
document.addEventListener('DOMContentLoaded', function() {
    // ... existing code ...
    initMarkAllReadButton();
});

// Обновлять видимость кнопки при получении новых сообщений
function handleNewMessage(data) {
    // ... existing code ...
    updateMarkAllReadButtonVisibility();
} 