/**
 * GreenTalk - Современный чат
 * Основной JavaScript файл для работы с чатом
 */

// Полифилл для requestAnimationFrame для поддержки старых браузеров
(function() {
    var lastTime = 0;
    var vendors = ['ms', 'moz', 'webkit', 'o'];
    for(var x = 0; x < vendors.length && !window.requestAnimationFrame; ++x) {
        window.requestAnimationFrame = window[vendors[x]+'RequestAnimationFrame'];
        window.cancelAnimationFrame = window[vendors[x]+'CancelAnimationFrame'] 
                                   || window[vendors[x]+'CancelRequestAnimationFrame'];
    }
 
    if (!window.requestAnimationFrame)
        window.requestAnimationFrame = function(callback, element) {
            var currTime = new Date().getTime();
            var timeToCall = Math.max(0, 16 - (currTime - lastTime));
            var id = window.setTimeout(function() { callback(currTime + timeToCall); }, 
              timeToCall);
            lastTime = currTime + timeToCall;
            return id;
        };
 
    if (!window.cancelAnimationFrame)
        window.cancelAnimationFrame = function(id) {
            clearTimeout(id);
        };
}());

// Главный объект приложения
const Chat = {
    // Настройки
    settings: {
        socketUrl: window.location.origin,
        messageLoadCount: 20,
        typingTimeout: 2000,
        maxReconnectAttempts: 5,
        reconnectInterval: 3000,
        enableSounds: true,
        enableNotifications: true
    },

    // Состояние приложения
    state: {
        currentUser: null,
        currentChatType: null, // private, group
        currentChatRoom: null,
        currentChatPartner: null,
        currentGroupId: null,
        chats: [],
        messages: {},
        typingUsers: {},
        lastTypingTime: {},
        reconnectAttempts: 0,
        isRecording: false,
        recordingStartTime: null,
        mediaRecorder: null,
        recordedChunks: [],
        audioContext: null,
        replyingTo: null,
        editingMessage: null,
        searchQuery: '',
        isSocketConnected: false,
        darkMode: false,
        activeFilter: 'all',
        pendingRoomJoin: null
    },

    // DOM элементы
    elements: {},

    // Socket.IO соединение
    socket: null,

    /**
     * Инициализация приложения
     */
    init: function() {
        console.log('Инициализация чата GreenTalk...');
        this.loadElements();
        this.initSocket();
        this.setupEventListeners();
        this.getCurrentUser();
        this.loadChatList();
        this.setupTheme();
        this.setupAttachmentModal();
        this.setupNotificationSound();
        this.requestNotificationPermission();
        this.setupMessageContextMenu();
    },

    /**
     * Загрузка DOM элементов
     */
    loadElements: function() {
        this.elements = {
            // Контейнеры
            sidebar: document.querySelector('.sidebar'),
            chatContent: document.querySelector('.chat-content'),
            messagesContainer: document.getElementById('messagesContainer'),
            messageFormContainer: document.getElementById('messageFormContainer'),
            
            // Информация о чате
            chatInfo: document.getElementById('chatInfo'),
            noChatSelected: document.querySelector('.no-chat-selected'),
            activeChatInfo: document.querySelector('.active-chat-info'),
            chatName: document.getElementById('chatName'),
            chatStatus: document.getElementById('chatStatus'),
            chatAvatarImg: document.getElementById('chatAvatarImg'),
            chatStatusIndicator: document.getElementById('chatStatusIndicator'),
            
            // Кнопки действий
            callBtn: document.getElementById('callBtn'),
            videoCallBtn: document.getElementById('videoCallBtn'),
            chatMenuBtn: document.getElementById('chatMenuBtn'),
            
            // Профиль пользователя
            userAvatar: document.getElementById('userAvatar'),
            userName: document.getElementById('userName'),
            userProfileMenu: document.getElementById('userProfileMenu'),
            
            // Поиск и фильтры
            searchInput: document.getElementById('searchInput'),
            clearSearchBtn: document.getElementById('clearSearchBtn'),
            filterBtns: document.querySelectorAll('.filter-btn'),
            
            // Список чатов
            chatsList: document.getElementById('chatsList'),
            
            // Форма отправки
            messageInput: document.getElementById('messageInput'),
            sendMessageBtn: document.getElementById('sendMessageBtn'),
            emojiBtn: document.getElementById('emojiBtn'),
            fileBtn: document.getElementById('fileBtn'),
            imageBtn: document.getElementById('imageBtn'),
            audioBtn: document.getElementById('audioBtn'),
            
            // Запись голосового сообщения
            recordingIndicator: document.getElementById('recordingIndicator'),
            cancelRecordingBtn: document.getElementById('cancelRecordingBtn'),
            
            // Контекстные меню
            messageContextMenu: document.getElementById('messageContextMenu'),
            chatContextMenu: document.getElementById('chatContextMenu'),
            
            // Модальные окна
            attachmentModal: document.getElementById('attachmentModal'),
            newGroupModal: document.getElementById('newGroupModal'),
            profileSettingsModal: document.getElementById('profileSettingsModal'),
            chatInfoModal: document.getElementById('chatInfoModal'),
            
            // Настройки темы
            toggleThemeBtn: document.getElementById('toggleThemeBtn'),
            settingsBtn: document.getElementById('settingsBtn'),
            
            // Кнопка нового чата
            newChatBtn: document.getElementById('newChatBtn'),
            
            // Аудио для уведомлений
            notificationSound: null
        };
    },

    /**
     * Инициализация Socket.IO
     */
    initSocket: function() {
        console.log('Инициализация Socket.IO...');
        
        this.socket = io(this.settings.socketUrl, {
            reconnection: true,
            reconnectionAttempts: this.settings.maxReconnectAttempts,
            reconnectionDelay: this.settings.reconnectInterval
        });
        
        this.setupSocketListeners();
    },

    /**
     * Настройка обработчиков событий для Socket.IO
     */
    setupSocketListeners: function() {
        // Отписываемся от всех событий перед установкой новых обработчиков
        this.socket.off('connect');
        this.socket.off('disconnect');
        this.socket.off('reconnect');
        this.socket.off('reconnect_attempt');
        this.socket.off('reconnect_failed');
        this.socket.off('error');
        this.socket.off('receive_private_message');
        this.socket.off('user_typing');
        this.socket.off('user_stop_typing');
        this.socket.off('chat_cleared');
        this.socket.off('message_deleted');
        this.socket.off('message_edited');
        this.socket.off('load_private_history');
        this.socket.off('join_success');
        this.socket.off('user_status_changed');
        this.socket.off('new_chat_created');
        this.socket.off('chat_update');
        this.socket.off('message_read');
        
        // Устанавливаем новые обработчики
        this.socket.on('connect', () => {
            console.log('🔌 Подключено к Socket.IO');
            
            // Присоединяемся к личной комнате после подключения
            this.joinPersonalRoom();
            
            // Если у нас есть текущий чат, присоединяемся к его комнате
            if (this.state.currentChatRoom) {
                this.joinChatRoom(this.state.currentChatRoom);
            }
        });
        
        this.socket.on('disconnect', () => {
            console.log('🔌 Отключено от Socket.IO');
        });
        
        this.socket.on('reconnect', (attemptNumber) => {
            console.log(`🔄 Переподключено к Socket.IO после ${attemptNumber} попыток`);
            
            // Повторно присоединяемся к комнатам после переподключения
            this.joinPersonalRoom();
            
            if (this.state.currentChatRoom) {
                this.joinChatRoom(this.state.currentChatRoom);
            }
        });
        
        this.socket.on('reconnect_attempt', (attemptNumber) => {
            console.log(`🔄 Попытка переподключения к Socket.IO #${attemptNumber}...`);
        });
        
        this.socket.on('reconnect_failed', () => {
            console.log('❌ Переподключение к Socket.IO не удалось');
        });
        
        this.socket.on('error', (error) => {
            console.error('🚨 Ошибка Socket.IO:', error);
        });
        
        // Основной обработчик входящих сообщений
        this.socket.on('receive_private_message', (data) => {
            console.log('📨 Получено приватное сообщение:', data);
            
            // Добавляем сообщение в текущий чат, если он открыт
            if (this.isMessageForCurrentChat(data)) {
                this.addMessageToChat(data);
                
                // Если это не наше сообщение, отправляем событие прочтения
                if (data.sender !== this.state.currentUser) {
                    this.updateUnreadStatus(data);
                }
            } else {
                // Обновляем список чатов и счетчик непрочитанных
                this.addUnreadMessage(data);
                this.updateChatListWithMessage(data);
            }
            
            // Проигрываем звук уведомления, если это не наше сообщение
            if (data.sender !== this.state.currentUser) {
                this.playNotificationSound();
                
                // Показываем браузерное уведомление, если вкладка не активна
                if (document.hidden && Notification.permission === 'granted') {
                    const notificationTitle = data.sender;
                    let notificationBody = '';
                    
                    // Проверяем, является ли сообщение файлом
                    if (data.message && typeof data.message === 'string' && data.message.startsWith('FILE:')) {
                        const parts = data.message.split(':');
                        if (parts.length >= 2) {
                            const fileType = parts[1];
                            switch (fileType) {
                                case 'image':
                                    notificationBody = 'Отправил(а) изображение';
                                    break;
                                case 'video':
                                    notificationBody = 'Отправил(а) видео';
                                    break;
                                case 'audio':
                                    notificationBody = 'Отправил(а) аудио';
                                    break;
                                case 'document':
                                    notificationBody = 'Отправил(а) документ';
                                    break;
                                case 'voice':
                                    notificationBody = 'Отправил(а) голосовое сообщение';
                                    break;
                                default:
                                    notificationBody = 'Отправил(а) файл';
                            }
                        }
                    } else {
                        // Обычное текстовое сообщение
                        notificationBody = data.message;
                        // Ограничиваем длину сообщения для уведомления
                        if (notificationBody.length > 100) {
                            notificationBody = notificationBody.substring(0, 97) + '...';
                        }
                    }
                    
                    const notification = new Notification(notificationTitle, {
                        body: notificationBody,
                        icon: '/static/img/logo-64.png'
                    });
                    
                    // Переходим в чат при клике на уведомление
                    notification.onclick = () => {
                        window.focus();
                        this.openChat(data.sender);
                    };
                }
            }
        });
        
        // Обработчик успешной отправки сообщения
        this.socket.on('message_sent', (data) => {
            console.log('✅ Сообщение успешно отправлено:', data);
        });
        
        this.socket.on('user_typing', (data) => {
            this.handleUserTyping(data);
        });
        
        this.socket.on('user_stop_typing', (data) => {
            this.handleUserStopTyping(data);
        });
        
        this.socket.on('chat_cleared', (data) => {
            this.handleChatCleared(data);
        });
        
        this.socket.on('message_deleted', (data) => {
            this.handleMessageDeleted(data);
        });
        
        this.socket.on('message_edited', (data) => {
            this.handleMessageEdited(data);
        });
        
        // Обработчик загрузки истории сообщений
        this.socket.on('load_private_history', (data) => {
            console.log('Получен ответ с историей сообщений:', data);
            this.handleHistoryLoaded(data);
        });
        
        this.socket.on('join_success', (data) => {
            console.log('🔗 Успешно присоединился к комнате:', data.room);
        });
        
        this.socket.on('user_status_changed', (data) => {
            console.log('👤 Статус пользователя изменен:', data);
            
            // Обновляем статус в списке контактов и в шапке чата
            this.updateUserStatus(data.username, data.status);
        });
        
        // Обработчики обновлений списка чатов
        this.socket.on('new_chat_created', (data) => {
            console.log('💬 Создан новый чат:', data);
            
            // Добавляем новый чат в список
            this.loadChats();
        });
        
        this.socket.on('chat_update', (data) => {
            console.log('🔄 Обновление чата:', data);
            
            // Обновляем данные чата в списке
            this.updateChatData(data);
        });
        
        // Обработчик события прочтения сообщения
        this.socket.on('message_read', (data) => {
            console.log('✓ Сообщение прочитано:', data);
            
            // Обновляем статус прочтения сообщения в интерфейсе
            this.updateMessageReadStatus(data.message_id, data.read_by);
        });
    },

    /**
     * Настройка обработчиков событий для UI элементов
     */
    setupEventListeners: function() {
        // Обработчик отправки сообщения
        this.elements.sendMessageBtn.addEventListener('click', (e) => {
            e.preventDefault();
            this.sendMessage();
        });
        
        // Отправка сообщения по Enter
        this.elements.messageInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });
        
        // Эффект "печатает" при вводе
        this.elements.messageInput.addEventListener('input', () => {
            this.handleTyping();
        });
        
        // Обработчик поиска по чатам
        this.elements.searchInput.addEventListener('input', () => {
            this.state.searchQuery = this.elements.searchInput.value.toLowerCase();
            this.filterChats();
        });
        
        // Очистка поля поиска
        this.elements.clearSearchBtn.addEventListener('click', () => {
            this.elements.searchInput.value = '';
            this.state.searchQuery = '';
            this.filterChats();
        });
        
        // Обработчик фильтров чатов
        this.elements.filterBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                this.elements.filterBtns.forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                this.filterChatsByType(btn.dataset.filter);
            });
        });
        
        // Обработчик переключения темы
        this.elements.toggleThemeBtn.addEventListener('click', () => {
            this.toggleTheme();
        });
        
        // Обработчик настроек профиля
        this.elements.settingsBtn.addEventListener('click', () => {
            this.openProfileSettings();
        });
        
        // Обработчик создания нового чата
        this.elements.newChatBtn.addEventListener('click', () => {
            this.showNewChatOptions();
        });
        
        // Обработчик нажатия на меню чата
        this.elements.chatMenuBtn.addEventListener('click', (e) => {
            this.showChatContextMenu(e);
        });
        
        // Обработчик записи голосового сообщения
        this.elements.audioBtn.addEventListener('click', () => {
            if (!this.state.currentChatRoom) {
                this.showError('Пожалуйста, выберите чат для отправки сообщения');
                return;
            }
            this.toggleVoiceRecording();
        });
        
        // Отмена записи голосового сообщения
        this.elements.cancelRecordingBtn.addEventListener('click', () => {
            this.cancelVoiceRecording();
        });
        
        // Открытие модального окна для прикрепления файлов
        this.elements.fileBtn.addEventListener('click', () => {
            if (!this.state.currentChatRoom) {
                this.showError('Пожалуйста, выберите чат для отправки файла');
                return;
            }
            this.openAttachmentModal();
        });
        
        // Обработчик загрузки изображений
        this.elements.imageBtn.addEventListener('click', () => {
            if (!this.state.currentChatRoom) {
                this.showError('Пожалуйста, выберите чат для отправки изображения');
                return;
            }
            this.uploadImage();
        });
        
        // Закрытие контекстных меню при клике вне
        document.addEventListener('click', (e) => {
            if (!e.target.closest('.context-menu')) {
                this.closeAllContextMenus();
            }
        });
        
        // Закрытие модальных окон при клике на крестик
        document.querySelectorAll('.close-modal').forEach(btn => {
            btn.addEventListener('click', () => {
                this.closeAllModals();
            });
        });
        
        // Закрытие модальных окон при клике на фон
        document.querySelectorAll('.modal').forEach(modal => {
            modal.addEventListener('click', (e) => {
                if (e.target === modal) {
                    this.closeAllModals();
                }
            });
        });
    },

    /**
     * Получение информации о текущем пользователе
     */
    getCurrentUser: function() {
        // Получаем имя пользователя из элемента userName
        this.state.currentUser = this.elements.userName.textContent.trim();
        console.log(`Текущий пользователь: ${this.state.currentUser}`);
        
        // Загружаем дополнительную информацию о пользователе
        fetch('/api/user')
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    // Обновляем аватар, если он есть
                    if (data.user.avatar_url) {
                        this.elements.userAvatar.src = data.user.avatar_url;
                    }
                    
                    // Обновляем статус
                    if (data.user.status) {
                        this.elements.userStatus.textContent = data.user.status;
                    }
                    
                    console.log('Информация о пользователе загружена');
                }
            })
            .catch(error => {
                console.error('Ошибка при загрузке информации о пользователе:', error);
            });
    },

    /**
     * Загрузка списка чатов
     */
    loadChatList: function() {
        console.log('Загрузка списка чатов...');
        
        fetch('/api/chats')
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    // Даже при успешном ответе могут быть ошибки декомпрессии
                    if (data.error_message) {
                        console.warn('Предупреждение при загрузке чатов:', data.error_message);
                        this.showError(data.error_message);
                    }
                    
                    // Всегда обновляем список чатов, даже если были ошибки
                    this.state.chats = data.chats || [];
                    this.renderChatList();
                    console.log(`Загружено ${this.state.chats.length} чатов`);
                } else {
                    throw new Error(data.error || 'Ошибка загрузки списка чатов');
                }
            })
            .catch(error => {
                console.error('Ошибка при загрузке списка чатов:', error);
                this.showError('Не удалось загрузить список чатов. Пожалуйста, обновите страницу или попробуйте позже.');
            });
    },

    /**
     * Отрисовка списка чатов
     */
    renderChatList: function() {
        console.log('Отрисовка списка чатов');
        const chatsList = this.elements.chatsList;
        
        // Очищаем текущий список
        chatsList.innerHTML = '';
        
        if (!this.state.chats || this.state.chats.length === 0) {
            chatsList.innerHTML = '<div class="no-chats">У вас пока нет чатов</div>';
            return;
        }
        
        // Фильтрация и сортировка чатов
        let filteredChats = this.state.chats;
        
        // Применяем фильтр поиска, если есть
        if (this.state.searchQuery) {
            filteredChats = filteredChats.filter(chat => {
                const name = (chat.user && chat.user.display_name) || chat.name || '';
                const lastMessage = (chat.last_message && chat.last_message.text) || '';
                return name.toLowerCase().includes(this.state.searchQuery) || 
                       lastMessage.toLowerCase().includes(this.state.searchQuery);
            });
        }
        
        // Применяем фильтр типа чата
        if (this.state.activeFilter !== 'all') {
            filteredChats = filteredChats.filter(chat => {
                if (this.state.activeFilter === 'private') {
                    return !chat.id.includes('group_');
                } else if (this.state.activeFilter === 'groups') {
                    return chat.id.includes('group_');
                } else if (this.state.activeFilter === 'favorites') {
                    return chat.is_favorite;
                }
                return true;
            });
        }
        
        // Сортируем по времени последнего сообщения (новые сверху)
        filteredChats.sort((a, b) => {
            const timeA = a.last_message ? a.last_message.timestamp : 0;
            const timeB = b.last_message ? b.last_message.timestamp : 0;
            return timeB - timeA;
        });
        
        // Проверяем общее количество непрочитанных сообщений
        let totalUnreadCount = 0;
        filteredChats.forEach(chat => {
            totalUnreadCount += chat.unread_count || 0;
        });
        
        // Если много непрочитанных сообщений (больше 5), добавляем кнопку "Отметить все как прочитанное"
        if (totalUnreadCount > 5) {
            const markAllReadBtn = document.createElement('div');
            markAllReadBtn.className = 'mark-all-read-btn';
            markAllReadBtn.innerHTML = `
                <i class="fas fa-check-double"></i>
                <span>Отметить все как прочитанное</span>
            `;
            
            // Добавляем обработчик клика для отметки всех сообщений как прочитанных
            markAllReadBtn.addEventListener('click', (e) => {
                e.stopPropagation(); // Предотвращаем всплытие события
                this.markAllAsRead();
            });
            
            // Добавляем кнопку в начало списка чатов
            chatsList.appendChild(markAllReadBtn);
        }
        
        // Отрисовываем каждый чат
        filteredChats.forEach(chat => {
            const chatItem = document.createElement('div');
            chatItem.className = 'chat-item';
            chatItem.setAttribute('data-chat-id', chat.id);
            
            // Если это текущий активный чат, добавляем класс active
            if (chat.id === this.state.currentChatRoom) {
                chatItem.classList.add('active');
            }
            
            // Получаем данные пользователя для отображения (для приватных чатов)
            const partner = chat.user || { 
                username: chat.id.split('_').pop(),
                display_name: chat.id.split('_').pop(),
                avatar_url: '/static/img/default-avatar.png'
            };
            
            // Определяем последнее сообщение
            const lastMessage = chat.last_message || { text: 'Нет сообщений', timestamp: 0 };
            
            // Форматируем время
            const timestamp = lastMessage.timestamp ? this.formatTime(new Date(lastMessage.timestamp * 1000)) : '';
            
            // Сокращаем слишком длинный текст сообщения
            let messageText = lastMessage.text || '';
            let messageIcon = '';
            
            // Проверяем, если это файловое сообщение (FILE:тип:url)
            if (messageText.startsWith('FILE:')) {
                const parts = messageText.split(':');
                if (parts.length >= 2) {
                    const fileType = parts[1];
                    
                    // Определяем иконку и текст в зависимости от типа файла
                    switch (fileType) {
                        case 'image':
                            messageText = 'Фото';
                            messageIcon = '<i class="fas fa-image"></i> ';
                            break;
                        case 'video':
                            messageText = 'Видео';
                            messageIcon = '<i class="fas fa-video"></i> ';
                            break;
                        case 'audio':
                            messageText = 'Аудио';
                            messageIcon = '<i class="fas fa-music"></i> ';
                            break;
                        case 'voice':
                            messageText = 'Голосовое сообщение';
                            messageIcon = '<i class="fas fa-microphone"></i> ';
                            break;
                        case 'document':
                            messageText = 'Документ';
                            messageIcon = '<i class="fas fa-file-alt"></i> ';
                            break;
                        default:
                            messageText = 'Файл';
                            messageIcon = '<i class="fas fa-file"></i> ';
                    }
                }
            } else if (messageText.length > 30) {
                messageText = messageText.substring(0, 27) + '...';
            }

            // Подготавливаем аватар пользователя
            let avatarContent;
            if (partner.avatar_url) {
                avatarContent = `<img src="${partner.avatar_url}" alt="${partner.display_name}">`;
            } else {
                // Если аватара нет, показываем первую букву имени
                const initial = partner.display_name.charAt(0).toUpperCase();
                avatarContent = `<div class="no-avatar">${initial}</div>`;
            }
            
            // Создаем HTML для элемента чата
            chatItem.innerHTML = `
                <div class="chat-item-avatar">
                    ${avatarContent}
                    <div class="status-indicator ${partner.status === 'online' ? 'online' : 'offline'}"></div>
                </div>
                <div class="chat-item-content">
                    <div class="chat-item-header">
                        <h5 class="chat-item-name">${partner.display_name}</h5>
                        <span class="chat-item-time">${timestamp}</span>
                    </div>
                    <div class="chat-item-message">
                        <p class="chat-item-last-msg">${messageIcon}${messageText}</p>
                        <div class="chat-item-badges">
                            ${chat.unread_count ? `<span class="unread-badge">${chat.unread_count}</span>` : ''}
                            ${chat.is_favorite ? '<span class="favorite-badge"><i class="fas fa-star"></i></span>' : ''}
                        </div>
                    </div>
                </div>
            `;
            
            // Добавляем класс new-message, если есть непрочитанные сообщения
            if (chat.unread_count > 0) {
                chatItem.classList.add('new-message');
            }
            
            // Добавляем обработчик клика для открытия чата
            chatItem.addEventListener('click', () => {
                this.openChat(chat.id, chat.id.includes('group_') ? 'group' : 'private', partner.username);
            });
            
            // Добавляем в список
            chatsList.appendChild(chatItem);
        });
        
        // Если после фильтрации список пуст, показываем сообщение
        if (filteredChats.length === 0) {
            if (this.state.searchQuery) {
                chatsList.innerHTML = '<div class="no-chats">Чаты не найдены</div>';
            } else {
                chatsList.innerHTML = '<div class="no-chats">У вас пока нет чатов</div>';
            }
        }
    },

    /**
     * Фильтрация чатов по поисковому запросу
     */
    filterChats: function() {
        console.log('Фильтрация чатов по запросу:', this.state.searchQuery);
        // После фильтрации обновляем список
        this.renderChatList();
    },
    
    /**
     * Фильтрация чатов по типу
     * @param {string} filterType - Тип фильтра (all, private, groups, favorites)
     */
    filterChatsByType: function(filterType) {
        console.log('Фильтрация чатов по типу:', filterType);
        this.state.activeFilter = filterType;
        // После фильтрации обновляем список
        this.renderChatList();
    },

    /**
     * Настройка темы приложения
     */
    setupTheme: function() {
        // Проверяем, есть ли сохраненное значение темы
        const savedTheme = localStorage.getItem('theme');
        
        if (savedTheme === 'dark') {
            document.documentElement.setAttribute('data-bs-theme', 'dark');
            this.state.darkMode = true;
        } else {
            document.documentElement.setAttribute('data-bs-theme', 'light');
            this.state.darkMode = false;
        }
    },

    /**
     * Переключение темы (светлая/темная)
     */
    toggleTheme: function() {
        if (this.state.darkMode) {
            document.documentElement.setAttribute('data-bs-theme', 'light');
            localStorage.setItem('theme', 'light');
            this.state.darkMode = false;
        } else {
            document.documentElement.setAttribute('data-bs-theme', 'dark');
            localStorage.setItem('theme', 'dark');
            this.state.darkMode = true;
        }
    },

    /**
     * Показать опции создания нового чата
     */
    showNewChatOptions: function() {
        console.log('Показываем опции создания нового чата');
        
        // Создаем элемент модального окна для выбора типа чата, если его еще нет
        let newChatModal = document.getElementById('newChatModal');
        
        if (!newChatModal) {
            // Создаем модальное окно
            newChatModal = document.createElement('div');
            newChatModal.id = 'newChatModal';
            newChatModal.className = 'modal';
            
            // Создаем содержимое модального окна
            newChatModal.innerHTML = `
                <div class="modal-content">
                    <div class="modal-header">
                        <h3>Новый чат</h3>
                        <button class="close-modal">&times;</button>
                    </div>
                    <div class="modal-body">
                        <div class="new-chat-options">
                            <div class="option" data-type="private">
                                <div class="option-icon"><i class="fas fa-user"></i></div>
                                <span>Личный чат</span>
                            </div>
                            <div class="option" data-type="group">
                                <div class="option-icon"><i class="fas fa-users"></i></div>
                                <span>Групповой чат</span>
                            </div>
                        </div>
                        <div id="userSearchContainer" class="user-search-container" style="display: none;">
                            <div class="search-box">
                                <i class="fas fa-search"></i>
                                <input type="text" id="userSearchInput" placeholder="Введите имя пользователя...">
                            </div>
                            <div id="userSearchResults" class="user-search-results"></div>
                        </div>
                    </div>
                </div>
            `;
            
            // Добавляем модальное окно в DOM
            document.body.appendChild(newChatModal);
            
            // Добавляем обработчики событий
            newChatModal.querySelector('.close-modal').addEventListener('click', () => {
                newChatModal.style.display = 'none';
            });
            
            newChatModal.addEventListener('click', (e) => {
                if (e.target === newChatModal) {
                    newChatModal.style.display = 'none';
                }
            });
            
            // Обработчик выбора типа чата
            const options = newChatModal.querySelectorAll('.option');
            options.forEach(option => {
                option.addEventListener('click', () => {
                    const type = option.dataset.type;
                    if (type === 'private') {
                        // Показать поиск пользователей
                        this.showUserSearch();
                    } else if (type === 'group') {
                        // Открыть модальное окно создания группы
                        newChatModal.style.display = 'none';
                        this.elements.newGroupModal.style.display = 'block';
                    }
                });
            });
            
            // Обработчик поиска пользователей
            const userSearchInput = document.getElementById('userSearchInput');
            userSearchInput.addEventListener('input', () => {
                this.searchUsers(userSearchInput.value);
            });
        }
        
        // Показываем модальное окно
        newChatModal.style.display = 'block';
    },
    
    /**
     * Показать интерфейс поиска пользователей
     */
    showUserSearch: function() {
        const userSearchContainer = document.getElementById('userSearchContainer');
        userSearchContainer.style.display = 'block';
        
        // Фокус на поле ввода
        const userSearchInput = document.getElementById('userSearchInput');
        userSearchInput.focus();
        
        // Очищаем предыдущие результаты
        const userSearchResults = document.getElementById('userSearchResults');
        userSearchResults.innerHTML = '';
    },
    
    /**
     * Поиск пользователей
     * @param {string} query - Поисковый запрос
     */
    searchUsers: function(query) {
        if (!query || query.length < 2) {
            // Очищаем результаты, если запрос слишком короткий
            const userSearchResults = document.getElementById('userSearchResults');
            userSearchResults.innerHTML = '';
            return;
        }
        
        console.log(`Поиск пользователей по запросу: ${query}`);
        
        // Запрос к API
        fetch(`/api/search_users?query=${encodeURIComponent(query)}`)
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    this.renderUserSearchResults(data.users);
                } else {
                    console.error('Ошибка при поиске пользователей:', data.error);
                }
            })
            .catch(error => {
                console.error('Ошибка запроса при поиске пользователей:', error);
            });
    },
    
    /**
     * Отрисовка результатов поиска пользователей
     * @param {Array} users - Список найденных пользователей
     */
    renderUserSearchResults: function(users) {
        const userSearchResults = document.getElementById('userSearchResults');
        userSearchResults.innerHTML = '';
        
        if (users.length === 0) {
            userSearchResults.innerHTML = '<div class="no-results">Пользователи не найдены</div>';
            return;
        }
        
        users.forEach(user => {
            const userItem = document.createElement('div');
            userItem.className = 'user-item';
            userItem.dataset.username = user.username;
            
            userItem.innerHTML = `
                <div class="user-avatar">
                    <img src="${user.avatar_url}" alt="${user.name}">
                    <div class="status-indicator ${user.status === 'online' ? 'online' : 'offline'}"></div>
                </div>
                <div class="user-info">
                    <div class="user-name">${user.name}</div>
                    <div class="user-username">@${user.username}</div>
                </div>
            `;
            
            // Обработчик выбора пользователя
            userItem.addEventListener('click', () => {
                this.startChatWithUser(user.username);
            });
            
            userSearchResults.appendChild(userItem);
        });
    },
    
    /**
     * Начать чат с пользователем
     * @param {string} username - Имя пользователя
     */
    startChatWithUser: function(username) {
        console.log(`Начинаем чат с пользователем: ${username}`);
        
        // Скрываем все модальные окна
        this.closeAllModals();
        
        // Формируем идентификатор комнаты для приватного чата
        const roomId = `private_${this.state.currentUser}_${username}`;
        
        // Проверяем, существует ли уже такой чат
        const existingChat = this.state.chats.find(chat => 
            chat.type === 'private' && 
            (chat.partner === username || 
             (chat.id === roomId || chat.id === `private_${username}_${this.state.currentUser}`))
        );
        
        if (existingChat) {
            // Если чат существует, открываем его
            this.openChat(existingChat.id, 'private', username);
        } else {
            // Если чата нет, создаем новый и добавляем в список
            const newChat = {
                id: roomId,
                type: 'private',
                partner: username,
                name: username,
                last_message: 'Начало чата',
                timestamp: Date.now() / 1000,
                unread: 0,
                is_favorite: false,
                is_blocked: false,
                status: 'offline'
            };
            
            // Добавляем чат в список
            this.state.chats.unshift(newChat);
            
            // Обновляем отображение списка чатов
            this.renderChatList();
            
            // Открываем новый чат
            this.openChat(roomId, 'private', username);
            
            // Загружаем информацию о пользователе (аватар, статус и т.д.)
            this.loadUserInfo(username);
        }
    },
    
    /**
     * Закрыть все модальные окна
     */
    closeAllModals: function() {
        // Скрываем все модальные окна
        const modals = document.querySelectorAll('.modal');
        modals.forEach(modal => {
            modal.style.display = 'none';
        });
        
        // Скрываем модальное окно для нового чата, если оно существует
        const newChatModal = document.getElementById('newChatModal');
        if (newChatModal) {
            newChatModal.style.display = 'none';
        }
    },
    
    /**
     * Открыть чат
     * @param {string} roomId - Идентификатор комнаты
     * @param {string} type - Тип чата (private/group)
     * @param {string} partner - Имя собеседника или ID группы
     */
    openChat: function(roomId, type, partner) {
        console.log(`Открытие чата: ${roomId}, тип: ${type}, партнер: ${partner}`);
        
        // Присоединяемся к комнате Socket.IO
        this.joinChatRoom(roomId);
        
        // Обновляем состояние
        this.state.currentChatRoom = roomId;
        this.state.currentChatType = type;
        
        if (type === 'private') {
            this.state.currentChatPartner = partner;
            
            // Принудительно сбрасываем счетчик непрочитанных сообщений в чате
            const chatIndex = this.state.chats.findIndex(chat => 
                chat.id === roomId || 
                chat.id.includes(partner) || 
                chat.partner === partner
            );
            
            if (chatIndex !== -1) {
                this.state.chats[chatIndex].unread_count = 0;
            }
        } else if (type === 'group') {
            this.state.currentGroupId = partner; // Для групп partner содержит ID группы
        }
        
        // Обновляем интерфейс
        this.updateChatUI();
        
        // Загружаем историю сообщений
        this.loadChatHistory();
        
        // Отмечаем все сообщения в этом чате как прочитанные через REST API
        this.markAsRead();
        
        // Обновляем список чатов для отображения изменений
        this.renderChatList();
    },
    
    /**
     * Присоединиться к комнате чата через Socket.IO
     * @param {string} roomId - Идентификатор комнаты
     */
    joinChatRoom: function(roomId) {
        if (!this.state.isSocketConnected) {
            console.log('Невозможно присоединиться к комнате: соединение не установлено');
            // Запоминаем комнату для повторного подключения, когда соединение восстановится
            this.state.pendingRoomJoin = roomId;
            return;
        }
        
        console.log(`Присоединение к комнате: ${roomId}`);
        
        // Отправляем запрос на присоединение к комнате
        this.socket.emit('join_private', { room: roomId }, (response) => {
            if (response && response.success) {
                console.log(`Успешно присоединились к комнате: ${roomId}`);
            } else if (response && response.error) {
                console.error(`Ошибка при присоединении к комнате: ${response.error}`);
            }
        });
        
        // Запрашиваем историю сообщений при присоединении к комнате
        setTimeout(() => {
            this.loadChatHistory();
        }, 300);
    },
    
    /**
     * Обновить интерфейс чата
     */
    updateChatUI: function() {
        // Показываем интерфейс активного чата
        this.elements.noChatSelected.style.display = 'none';
        this.elements.activeChatInfo.style.display = 'flex';
        this.elements.messageFormContainer.style.display = 'flex';
        
        // Находим информацию о чате в списке
        const chat = this.state.chats.find(c => c.id === this.state.currentChatRoom);
        
        if (chat) {
            // Обновляем заголовок и информацию о чате
            this.elements.chatName.textContent = chat.name || chat.partner;
            
            // Устанавливаем статус
            if (this.state.currentChatType === 'private') {
                this.elements.chatStatus.textContent = chat.status || 'offline';
                this.elements.chatStatusIndicator.className = `status-indicator ${chat.status === 'online' ? 'online' : 'offline'}`;
            } else {
                this.elements.chatStatus.textContent = `${chat.members_count || 0} участников`;
                this.elements.chatStatusIndicator.style.display = 'none';
            }
            
            // Обновляем аватар
            if (chat.avatar_url) {
                this.elements.chatAvatarImg.src = chat.avatar_url;
            } else {
                this.elements.chatAvatarImg.src = '/static/img/default-avatar.png';
            }
            
            // Показываем кнопки действий
            this.elements.chatMenuBtn.style.display = 'block';
            
            if (this.state.currentChatType === 'private') {
                this.elements.callBtn.style.display = 'block';
                this.elements.videoCallBtn.style.display = 'block';
            } else {
                this.elements.callBtn.style.display = 'none';
                this.elements.videoCallBtn.style.display = 'none';
            }
        }
    },
    
    /**
     * Загрузить историю сообщений
     */
    loadChatHistory: function() {
        console.log(`Загрузка истории сообщений для комнаты: ${this.state.currentChatRoom}`);
        
        // Очищаем контейнер сообщений
        this.elements.messagesContainer.innerHTML = '';
        
        // Показываем индикатор загрузки
        const loadingIndicator = document.createElement('div');
        loadingIndicator.className = 'loading-indicator';
        loadingIndicator.innerHTML = '<div class="spinner"></div>';
        this.elements.messagesContainer.appendChild(loadingIndicator);
        
        // Запрашиваем историю через Socket.IO
        this.socket.emit('load_private_history', {
            room: this.state.currentChatRoom,
            count: this.settings.messageLoadCount
        });
    },
    
    /**
     * Обработка загруженной истории сообщений
     * @param {Object} data - Данные с историей сообщений
     */
    handleHistoryLoaded: function(data) {
        console.log('Получена история сообщений:', data);
        
        // Удаляем индикатор загрузки, если он есть
        const loadingIndicator = this.elements.messagesContainer.querySelector('.loading-indicator');
        if (loadingIndicator) {
            loadingIndicator.remove();
        }
        
        // Проверяем, есть ли ошибка
        if (data.error) {
            console.error('Ошибка при загрузке истории сообщений:', data.error);
            // Показываем сообщение об ошибке в контейнере
            const errorMessage = document.createElement('div');
            errorMessage.className = 'error-message';
            errorMessage.textContent = 'Ошибка при загрузке сообщений: ' + data.error;
            this.elements.messagesContainer.appendChild(errorMessage);
            return;
        }
        
        // Получаем сообщения
        const messages = data.messages || [];
        
        console.log('Количество полученных сообщений:', messages.length);
        if (messages.length > 0) {
            console.log('Пример первого сообщения:', messages[0]);
        }
        
        if (messages.length === 0) {
            // Если сообщений нет, показываем соответствующее уведомление
            const emptyMessage = document.createElement('div');
            emptyMessage.className = 'empty-chat-message';
            emptyMessage.textContent = 'Нет сообщений. Начните общение прямо сейчас!';
            this.elements.messagesContainer.appendChild(emptyMessage);
            return;
        }
        
        // Находим текущий чат и проверяем количество непрочитанных сообщений
        const currentChat = this.state.chats.find(chat => 
            chat.id === this.state.currentChatRoom || 
            (chat.partner === this.state.currentChatPartner)
        );
        
        // Если непрочитанных сообщений больше 5, показываем кнопку "Отметить все как прочитанное"
        if (currentChat && currentChat.unread_count > 5) {
            // Добавляем элемент стилей для кнопки, если его еще нет
            if (!document.getElementById('mark-read-btn-styles')) {
                const style = document.createElement('style');
                style.id = 'mark-read-btn-styles';
                style.textContent = `
                    .mark-all-read-btn {
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        padding: 10px 16px;
                        background-color: var(--hover-bg);
                        color: var(--primary-color);
                        border-radius: 8px;
                        margin: 12px auto;
                        cursor: pointer;
                        transition: background-color 0.2s ease;
                        max-width: 260px;
                        width: 100%;
                        font-size: 14px;
                        font-weight: 500;
                        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
                    }
                    .mark-all-read-btn:hover {
                        background-color: var(--active-bg);
                    }
                    .mark-all-read-btn i {
                        margin-right: 8px;
                        font-size: 16px;
                    }
                `;
                document.head.appendChild(style);
            }
            
            // Создаем кнопку
            const markAllReadBtn = document.createElement('div');
            markAllReadBtn.className = 'mark-all-read-btn';
            markAllReadBtn.innerHTML = `
                <i class="fas fa-check-double"></i>
                <span>Отметить все как прочитанное</span>
            `;
            
            // Добавляем обработчик клика
            markAllReadBtn.addEventListener('click', () => {
                this.markAllAsRead();
                // Удаляем кнопку после нажатия
                markAllReadBtn.remove();
                // Показываем уведомление
                this.showToast('Все сообщения отмечены как прочитанные');
            });
            
            // Добавляем кнопку в контейнер сообщений перед сообщениями
            this.elements.messagesContainer.appendChild(markAllReadBtn);
        }
        
        // Добавляем комнату к сообщениям, если её нет
        const processedMessages = messages.map(message => {
            console.log('Обработка сообщения:', message);
            if (!message.room) {
                // Если у сообщения нет поля room, добавляем текущую комнату
                return {
                    ...message, 
                    room: this.state.currentChatRoom
                };
            }
            return message;
        });
        
        // Группируем сообщения по дате
        const groupedMessages = this.groupMessagesByDate(processedMessages);
        console.log('Сгруппированные сообщения:', groupedMessages);
        
        // Отображаем сообщения
        this.renderMessages(groupedMessages);
        
        // Прокручиваем к последнему сообщению
        this.scrollToBottom();
    },
    
    /**
     * Группировка сообщений по дате
     * @param {Array} messages - Массив сообщений
     * @returns {Object} Сообщения, сгруппированные по дате
     */
    groupMessagesByDate: function(messages) {
        const grouped = {};
        
        // Сортируем сообщения по timestamp (старые сначала, новые в конце)
        messages.sort((a, b) => a.timestamp - b.timestamp);
        
        messages.forEach(message => {
            const date = new Date(message.timestamp * 1000);
            const dateStr = this.formatDate(date);
            
            if (!grouped[dateStr]) {
                grouped[dateStr] = [];
            }
            
            grouped[dateStr].push(message);
        });
        
        return grouped;
    },
    
    /**
     * Форматирование даты для отображения
     * @param {Date} date - Объект даты
     * @returns {string} Отформатированная дата
     */
    formatDate: function(date) {
        const today = new Date();
        const yesterday = new Date();
        yesterday.setDate(yesterday.getDate() - 1);
        
        if (date.toDateString() === today.toDateString()) {
            return 'Сегодня';
        } else if (date.toDateString() === yesterday.toDateString()) {
            return 'Вчера';
        } else {
            const day = date.getDate().toString().padStart(2, '0');
            const month = (date.getMonth() + 1).toString().padStart(2, '0');
            const year = date.getFullYear();
            return `${day}.${month}.${year}`;
        }
    },
    
    /**
     * Отрисовка сгруппированных сообщений
     * @param {Object} groupedMessages - Сообщения, сгруппированные по дате
     */
    renderMessages: function(groupedMessages) {
        // Очищаем контейнер сообщений
        this.elements.messagesContainer.innerHTML = '';
        
        // Для каждой даты создаем группу сообщений
        for (const date in groupedMessages) {
            // Добавляем разделитель с датой
            const dateDiv = document.createElement('div');
            dateDiv.className = 'message-date';
            dateDiv.innerHTML = `<span>${date}</span>`;
            this.elements.messagesContainer.appendChild(dateDiv);
            
            // Добавляем сообщения за эту дату
            const messages = groupedMessages[date];
            const messageGroup = document.createElement('div');
            messageGroup.className = 'message-group';
            
            messages.forEach(message => {
                const messageDiv = this.renderMessage(message);
                messageGroup.appendChild(messageDiv);
            });
            
            this.elements.messagesContainer.appendChild(messageGroup);
        }
    },
    
    /**
     * Отрисовка файлового сообщения
     * @param {string} fileType - Тип файла (image, video, audio, etc.)
     * @param {string} fileUrl - URL файла
     * @returns {string} HTML-разметка файлового сообщения
     */
    renderFileMessage: function(fileType, fileUrl) {
        // Извлекаем расширение файла для определения MIME типа
        const fileExtension = fileUrl.split('.').pop().toLowerCase();
        let mimeType = 'application/octet-stream';
        let displayName = 'Файл';
        
        // Определяем MIME тип на основе расширения
        if (['jpg', 'jpeg', 'png', 'gif', 'webp'].includes(fileExtension)) {
            fileType = 'image';
            mimeType = `image/${fileExtension === 'jpg' ? 'jpeg' : fileExtension}`;
            displayName = 'Изображение';
        } else if (['mp4', 'webm', 'mov'].includes(fileExtension)) {
            fileType = 'video';
            mimeType = `video/${fileExtension}`;
            displayName = 'Видео';
        } else if (['mp3', 'wav', 'ogg', 'opus', 'webm'].includes(fileExtension)) {
            fileType = 'audio';
            mimeType = `audio/${fileExtension === 'webm' ? 'webm' : fileExtension}`;
            displayName = 'Аудио';
        } else if (['pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt'].includes(fileExtension)) {
            fileType = 'document';
            displayName = 'Документ';
        }
        
        // Генерируем уникальный ID для элементов аудио/видео
        const uniqueId = 'media-' + Date.now() + '-' + Math.floor(Math.random() * 1000);
        
        switch (fileType) {
            case 'image':
                return `<div class="message-content">
                    <div class="message-media">
                        <img src="${fileUrl}" alt="Изображение" loading="lazy">
                    </div>
                    <div class="message-meta">
                        <span class="message-time">${this.formatTime(new Date())}</span>
                        <span class="message-status read"><i class="fas fa-check-double"></i></span>
                    </div>
                </div>`;
                
            case 'video':
                return `<div class="message-content">
                    <div class="message-media">
                        <video id="${uniqueId}" controls preload="metadata">
                            <source src="${fileUrl}" type="${mimeType}">
                            Ваш браузер не поддерживает видео.
                        </video>
                    </div>
                    <div class="message-meta">
                        <span class="message-time">${this.formatTime(new Date())}</span>
                        <span class="message-status read"><i class="fas fa-check-double"></i></span>
                    </div>
                </div>`;
                
            case 'audio':
            case 'voice':
                // Используем setTimeout с нулевой задержкой, чтобы выполнить после рендеринга
                const audioContent = `<div class="message-content">
                    <div class="message-audio" id="${uniqueId}">
                        <div class="audio-controls">
                            <button class="audio-play-btn">
                                <i class="fas fa-play"></i>
                            </button>
                            <div class="audio-progress">
                                <div class="audio-progress-bar" style="width: 0%"></div>
                            </div>
                            <span class="audio-time">00:00</span>
                        </div>
                        <audio src="${fileUrl}" preload="metadata"></audio>
                    </div>
                    <div class="message-meta">
                        <span class="message-time">${this.formatTime(new Date())}</span>
                        <span class="message-status read"><i class="fas fa-check-double"></i></span>
                    </div>
                </div>`;
                
                // Регистрируем обработчик, который будет вызван после добавления элемента в DOM
                this.pendingAudioInitializations = this.pendingAudioInitializations || [];
                this.pendingAudioInitializations.push({
                    id: uniqueId,
                    setup: () => {
                        const audioContainer = document.getElementById(uniqueId);
                        if (audioContainer) {
                            const playBtn = audioContainer.querySelector('.audio-play-btn');
                            const audioElement = audioContainer.querySelector('audio');
                            const progressBar = audioContainer.querySelector('.audio-progress-bar');
                            const timeDisplay = audioContainer.querySelector('.audio-time');
                            
                            if (playBtn && audioElement && progressBar && timeDisplay) {
                                // Обработчик клика по кнопке воспроизведения
                                playBtn.addEventListener('click', () => {
                                    if (audioElement.paused) {
                                        audioElement.play();
                                        playBtn.innerHTML = '<i class="fas fa-pause"></i>';
                                    } else {
                                        audioElement.pause();
                                        playBtn.innerHTML = '<i class="fas fa-play"></i>';
                                    }
                                });
                                
                                // Обновление прогресса воспроизведения
                                audioElement.addEventListener('timeupdate', () => {
                                    const currentTime = audioElement.currentTime;
                                    const duration = audioElement.duration || 1;
                                    const percent = (currentTime / duration) * 100;
                                    
                                    progressBar.style.width = `${percent}%`;
                                    
                                    // Форматирование времени (мм:сс)
                                    const minutes = Math.floor(currentTime / 60).toString().padStart(2, '0');
                                    const seconds = Math.floor(currentTime % 60).toString().padStart(2, '0');
                                    timeDisplay.textContent = `${minutes}:${seconds}`;
                                });
                                
                                // Обработчик окончания воспроизведения
                                audioElement.addEventListener('ended', () => {
                                    playBtn.innerHTML = '<i class="fas fa-play"></i>';
                                    progressBar.style.width = '0%';
                                    timeDisplay.textContent = '00:00';
                                });
                                
                                // Клик по прогресс-бару для перемотки
                                const progressContainer = audioContainer.querySelector('.audio-progress');
                                if (progressContainer) {
                                    progressContainer.addEventListener('click', (e) => {
                                        const rect = progressContainer.getBoundingClientRect();
                                        const clickPos = e.clientX - rect.left;
                                        const containerWidth = rect.width;
                                        const percent = clickPos / containerWidth;
                                        
                                        audioElement.currentTime = percent * audioElement.duration;
                                    });
                                }
                            }
                        }
                    }
                });
                
                return audioContent;
                
            default:
                // Получаем имя файла из URL
                const fileName = fileUrl.split('/').pop() || 'Файл';
                
                return `<div class="message-content">
                    <div class="message-file">
                        <div class="file-icon">
                            <i class="fas fa-file${fileType === 'document' ? '-alt' : ''}"></i>
                        </div>
                        <div class="file-details">
                            <p class="file-name">${fileName}</p>
                            <div class="file-meta">
                                <span>${displayName}</span>
                                <a href="${fileUrl}" target="_blank" class="file-download">Скачать</a>
                            </div>
                        </div>
                    </div>
                    <div class="message-meta">
                        <span class="message-time">${this.formatTime(new Date())}</span>
                        <span class="message-status read"><i class="fas fa-check-double"></i></span>
                    </div>
                </div>`;
        }
    },
    
    /**
     * Форматирование времени
     * @param {Date} date - Объект даты
     * @returns {string} Отформатированное время
     */
    formatTime: function(date) {
        const hours = date.getHours().toString().padStart(2, '0');
        const minutes = date.getMinutes().toString().padStart(2, '0');
        return `${hours}:${minutes}`;
    },
    
    /**
     * Экранирование HTML-символов
     * @param {string} text - Текст для экранирования
     * @returns {string} Экранированный текст
     */
    escapeHtml: function(text) {
        if (!text) return '';
        
        const map = {
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#039;'
        };
        
        return text.replace(/[&<>"']/g, m => map[m]);
    },
    
    /**
     * Прокрутка контейнера сообщений к последнему сообщению
     */
    scrollToBottom: function() {
        if (!this.elements.messagesContainer) return;
        
        // Используем requestAnimationFrame для гарантированной прокрутки после рендеринга
        requestAnimationFrame(() => {
            this.elements.messagesContainer.scrollTop = this.elements.messagesContainer.scrollHeight;
            
            // Дополнительная прокрутка через setTimeout для случаев, когда есть изображения или медиа
            setTimeout(() => {
                this.elements.messagesContainer.scrollTop = this.elements.messagesContainer.scrollHeight;
            }, 100);
        });
    },
    
    /**
     * Загрузка информации о пользователе
     * @param {string} username - Имя пользователя
     */
    loadUserInfo: function(username) {
        // Можно добавить запрос к API для получения подробной информации о пользователе
        // Например, для загрузки аватара, статуса и т.д.
    },

    /**
     * Обрабатывает ошибки без уведомления пользователя, только логирует их в консоль
     * @param {string} errorMessage - Сообщение об ошибке
     * @param {Error} [error] - Объект ошибки (опционально)
     */
    handleSilentError: function(errorMessage, error) {
        // Логируем ошибку в консоль для отладки
        console.error('[Тихая ошибка]', errorMessage);
        
        // Если передан объект ошибки, логируем его отдельно
        if (error instanceof Error) {
            console.error(error);
        }
        
        // В будущем здесь может быть отправка ошибок на сервер для аналитики
        // this.trackError(errorMessage, error);
    },

    /**
     * Отправка сообщения
     */
    sendMessage: function() {
        // Если нет комнаты или собеседника, выходим
        if (!this.state.currentChatRoom || !this.state.currentChatPartner) {
            this.showError('Пожалуйста, выберите чат для отправки сообщения');
            return;
        }
        
        // Получаем текст сообщения и очищаем поле ввода
        const messageText = this.elements.messageInput.value.trim();
        this.elements.messageInput.value = '';
        
        // Если сообщение пустое, выходим
        if (!messageText) {
            return;
        }
        
        // Создаем временное ID для сообщения
        const tempId = `temp-${Date.now()}`;
        
        // Создаем объект временного сообщения
        const tempMessage = {
            id: tempId,
            sender: this.state.currentUser,
            recipient: this.state.currentChatPartner,
            message: messageText,
            timestamp: Math.floor(Date.now() / 1000),
            room: this.state.currentChatRoom
        };
        
        // Отображаем временное сообщение
        try {
            console.log('🔄 Отображаем временное сообщение:', tempMessage);
            
            // Находим или создаем группу сообщений для текущей даты
            const dateStr = this.formatDate(new Date());
            let dateGroup = null;
            let messageGroup = null;
            
            // Ищем группу с этой датой
            const dateDivs = this.elements.messagesContainer.querySelectorAll('.message-date');
            for (let i = 0; i < dateDivs.length; i++) {
                if (dateDivs[i].textContent.trim() === dateStr) {
                    dateGroup = dateDivs[i];
                    messageGroup = dateGroup.nextElementSibling;
                    
                    if (messageGroup && messageGroup.classList.contains('message-group')) {
                        break;
                    } else {
                        dateGroup = null; // Сбрасываем, если следующий элемент не группа
                    }
                }
            }
            
            // Если не нашли группу, создаем новую
            if (!dateGroup) {
                // Удаляем сообщение о пустом чате, если оно есть
                const emptyMessage = this.elements.messagesContainer.querySelector('.empty-chat-message');
                if (emptyMessage) {
                    emptyMessage.remove();
                }
                
                // Удаляем приветственный экран, если он есть
                const welcomeScreen = this.elements.messagesContainer.querySelector('.welcome-screen');
                if (welcomeScreen) {
                    welcomeScreen.remove();
                }
                
                // Создаем разделитель с датой
                dateGroup = document.createElement('div');
                dateGroup.className = 'message-date';
                dateGroup.innerHTML = `<span>${dateStr}</span>`;
                this.elements.messagesContainer.appendChild(dateGroup);
                
                // Создаем группу сообщений
                messageGroup = document.createElement('div');
                messageGroup.className = 'message-group';
                this.elements.messagesContainer.appendChild(messageGroup);
            }
            
            // Добавляем сообщение в группу
            const messageElement = this.renderMessage(tempMessage);
            messageGroup.appendChild(messageElement);
            
            // Прокручиваем к последнему сообщению
            this.scrollToBottom();
        } catch (error) {
            this.handleSilentError('Ошибка при отображении временного сообщения', error);
        }
        
        // Останавливаем индикатор набора текста
        this.stopTyping();
        
        // Отправляем сообщение через Socket.IO с обработкой потенциальных ошибок
        try {
            console.log('📡 Отправка сообщения через сокет:', {
                room: this.state.currentChatRoom,
                receiver: this.state.currentChatPartner,
                message: messageText
            });
            
            // Важно! Используем callback функцию для получения подтверждения от сервера
            this.socket.emit('send_private_message', {
                room: this.state.currentChatRoom,
                receiver: this.state.currentChatPartner,
                message: messageText
            }, (response) => {
                // Обрабатываем ответ от сервера
                if (response && response.error) {
                    console.error('❌ Ошибка при отправке сообщения:', response.error);
                    
                    // Находим временное сообщение и добавляем индикатор ошибки
                    const tempMessageElement = document.querySelector(`[data-message-id="${tempId}"]`);
                    if (tempMessageElement) {
                        tempMessageElement.classList.add('error');
                        
                        // Добавляем индикатор ошибки
                        const statusIcon = tempMessageElement.querySelector('.message-status');
                        if (statusIcon) {
                            statusIcon.innerHTML = '<i class="fas fa-exclamation-circle"></i>';
                            statusIcon.title = 'Ошибка отправки';
                        }
                    }
                } else {
                    console.log('✅ Сообщение успешно отправлено и сохранено на сервере');
                }
            });
        } catch (error) {
            this.handleSilentError('Ошибка при отправке сообщения', error);
            
            // Находим временное сообщение и добавляем индикатор ошибки
            const tempMessage = document.querySelector(`[data-message-id="${tempId}"]`);
            if (tempMessage) {
                tempMessage.classList.add('error');
                
                // Добавляем индикатор ошибки
                const statusIcon = tempMessage.querySelector('.message-status');
                if (statusIcon) {
                    statusIcon.innerHTML = '<i class="fas fa-exclamation-circle"></i>';
                    statusIcon.title = 'Ошибка отправки';
                }
            }
        }
    },
    
    /**
     * Добавление нового сообщения к существующим
     * @param {Object} groupedMessages - Сгруппированные сообщения
     */
    renderMessageAppend: function(groupedMessages) {
        try {
            // Для каждой даты
            for (const date in groupedMessages) {
                if (!groupedMessages.hasOwnProperty(date)) continue;
                
                // Проверяем, есть ли уже разделитель с такой датой
                let dateDiv = null;
                let messageGroup = null;
                
                // Находим все разделители с датами
                const dateDivs = this.elements.messagesContainer.querySelectorAll('.message-date');
                
                for (let i = 0; i < dateDivs.length; i++) {
                    if (dateDivs[i].textContent.trim() === date) {
                        dateDiv = dateDivs[i];
                        // Следующий элемент после даты - группа сообщений
                        messageGroup = dateDiv.nextElementSibling;
                        if (messageGroup && messageGroup.classList.contains('message-group')) {
                            break;
                        } else {
                            // Если следующий элемент не группа сообщений, сбрасываем dateDiv
                            dateDiv = null;
                        }
                    }
                }
                
                // Если нет разделителя с такой датой, создаем новые
                if (!dateDiv) {
                    // Удаляем сообщение о пустом чате, если оно есть
                    const emptyMessage = this.elements.messagesContainer.querySelector('.empty-chat-message');
                    if (emptyMessage) {
                        emptyMessage.remove();
                    }
                    
                    // Удаляем приветственный экран, если он есть
                    const welcomeScreen = this.elements.messagesContainer.querySelector('.welcome-screen');
                    if (welcomeScreen) {
                        welcomeScreen.remove();
                    }
                    
                    dateDiv = document.createElement('div');
                    dateDiv.className = 'message-date';
                    dateDiv.innerHTML = `<span>${date}</span>`;
                    this.elements.messagesContainer.appendChild(dateDiv);
                    
                    messageGroup = document.createElement('div');
                    messageGroup.className = 'message-group';
                    this.elements.messagesContainer.appendChild(messageGroup);
                }
                
                // Добавляем сообщения в группу
                const messages = groupedMessages[date];
                
                messages.forEach(message => {
                    // Проверяем, не является ли сообщение уже добавленным (проверка по ID)
                    if (message.id) {
                        const existingMessage = messageGroup.querySelector(`[data-message-id="${message.id}"]`);
                        if (existingMessage) {
                            return; // Пропускаем уже добавленное сообщение
                        }
                    }
                    
                    // Также проверяем дубликаты по временной метке и содержимому
                    if (message.timestamp && message.message) {
                        const allMessages = messageGroup.querySelectorAll('.message');
                        for (let i = 0; i < allMessages.length; i++) {
                            const msgTime = allMessages[i].querySelector('.message-time');
                            const msgText = allMessages[i].querySelector('.message-text');
                            
                            if (msgTime && msgText) {
                                const existingTime = msgTime.textContent;
                                const newTime = this.formatTime(new Date(message.timestamp * 1000));
                                const existingText = msgText.textContent;
                                const newText = message.message;
                                
                                if (existingTime === newTime && existingText === newText) {
                                    return; // Пропускаем дубликат
                                }
                            }
                        }
                    }
                    
                    const messageDiv = this.renderMessage(message);
                    messageGroup.appendChild(messageDiv);
                });
            }
            
            // Прокручиваем к последнему сообщению
            this.scrollToBottom();
        } catch (error) {
            console.error('Ошибка при отображении сообщений:', error);
        }
    },

    /**
     * Настройка модального окна для прикрепления файлов
     */
    setupAttachmentModal: function() {
        // Setup the attachment modal
        const attachmentModal = document.getElementById('attachmentModal');
        if (attachmentModal) {
            // Скрываем модальное окно изначально (добавляем эту строку в начало)
            attachmentModal.style.display = 'none';
            
            const fileInput = document.getElementById('fileUploadInput');
            
            // Get UI elements
            const browseLink = attachmentModal.querySelector('.browse-link');
            const cancelBtn = attachmentModal.querySelector('.btn-cancel');
            const sendBtn = attachmentModal.querySelector('.btn-send');
            const closeBtn = attachmentModal.querySelector('.attachment-popup-close');
            const attachmentOptions = attachmentModal.querySelectorAll('.attachment-option');
            
            // Close modal function
            const closeModal = () => {
                attachmentModal.style.display = 'none';
            };
            
            // Add event listeners
            attachmentModal.addEventListener('click', (e) => {
                if (e.target === attachmentModal) {
                    closeModal();
                }
            });
            
            if (closeBtn) closeBtn.addEventListener('click', closeModal);
            if (cancelBtn) cancelBtn.addEventListener('click', closeModal);
            
            // File browse
            if (browseLink) {
                browseLink.addEventListener('click', () => {
                    if (fileInput) fileInput.click();
                });
            }
            
            // File selection
            if (fileInput) {
                fileInput.addEventListener('change', (e) => {
                    const files = e.target.files;
                    if (files.length > 0) {
                        const filesList = document.getElementById('selectedFilesList');
                        const selectedFilesContainer = attachmentModal.querySelector('.selected-files');
                        
                        if (filesList && selectedFilesContainer) {
                            // Clear previous selections
                            filesList.innerHTML = '';
                            
                            // Add each file to the list
                            for (let i = 0; i < files.length; i++) {
                                const file = files[i];
                                const fileItem = document.createElement('li');
                                fileItem.textContent = `${file.name} (${this.formatFileSize(file.size)})`;
                                filesList.appendChild(fileItem);
                            }
                            
                            // Show the selected files container
                            selectedFilesContainer.style.display = 'block';
                        }
                    }
                });
            }
            
            // Send button
            if (sendBtn) {
                sendBtn.addEventListener('click', () => {
                    if (fileInput && fileInput.files.length > 0) {
                        this.uploadFile(fileInput.files[0]);
                        closeModal();
                    }
                });
            }
            
            // Attachment options
            attachmentOptions.forEach(option => {
                option.addEventListener('click', () => {
                    const type = option.getAttribute('data-type');
                    
                    // Set accepted file types based on the selected option
                    if (fileInput) {
                        switch (type) {
                            case 'image':
                                fileInput.accept = 'image/*';
                                break;
                            case 'video':
                                fileInput.accept = 'video/*';
                                break;
                            case 'audio':
                                fileInput.accept = 'audio/*';
                                break;
                            case 'document':
                                fileInput.accept = '.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt';
                                break;
                            default:
                                fileInput.accept = '';
                        }
                        
                        fileInput.click();
                    }
                });
            });
            
            // Удаляем эту строку, так как теперь она перенесена в начало функции
            // attachmentModal.style.display = 'none';
        }
    },

    /**
     * Открыть модальное окно для прикрепления файлов
     */
    openAttachmentModal: function() {
        if (!this.state.currentChatRoom) {
            console.log('Нужно выбрать чат перед прикреплением файлов');
            return;
        }
        
        // Вместо модального окна создаем выпадающее меню
        let fileMenu = document.getElementById('fileAttachmentMenu');
        
        if (!fileMenu) {
            // Создаем меню, если его еще нет
            fileMenu = document.createElement('div');
            fileMenu.id = 'fileAttachmentMenu';
            fileMenu.className = 'attachment-menu';
            fileMenu.innerHTML = `
                <div class="attachment-menu-item" data-type="image">
                    <i class="fas fa-image"></i>
                    <span>Фото</span>
                </div>
                <div class="attachment-menu-item" data-type="video">
                    <i class="fas fa-video"></i>
                    <span>Видео</span>
                </div>
                <div class="attachment-menu-item" data-type="audio">
                    <i class="fas fa-music"></i>
                    <span>Аудио</span>
                </div>
                <div class="attachment-menu-item" data-type="document">
                    <i class="fas fa-file-alt"></i>
                    <span>Документ</span>
                </div>
                <div class="attachment-menu-item" data-type="location">
                    <i class="fas fa-map-marker-alt"></i>
                    <span>Локация</span>
                </div>
                <div class="attachment-menu-item" data-type="contact">
                    <i class="fas fa-user"></i>
                    <span>Контакт</span>
                </div>
            `;
            
            // Добавляем в DOM рядом с кнопкой файла
            document.body.appendChild(fileMenu);
            
            // Добавляем CSS для выпадающего меню
            const style = document.createElement('style');
            style.textContent = `
                .attachment-menu {
                    position: absolute;
                    bottom: 60px;
                    background-color: var(--bg-color);
                    border-radius: 12px;
                    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
                    padding: 8px;
                    display: grid;
                    grid-template-columns: repeat(3, 1fr);
                    gap: 8px;
                    z-index: 1000;
                    width: auto;
                    max-width: 320px;
                    transform: translateY(20px);
                    opacity: 0;
                    transition: transform 0.3s ease, opacity 0.3s ease;
                }
                
                .attachment-menu.show {
                    transform: translateY(0);
                    opacity: 1;
                }
                
                .attachment-menu-item {
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                    justify-content: center;
                    padding: 12px;
                    border-radius: 8px;
                    cursor: pointer;
                    transition: background-color 0.2s ease;
                }
                
                .attachment-menu-item:hover {
                    background-color: var(--hover-color);
                }
                
                .attachment-menu-item i {
                    font-size: 24px;
                    margin-bottom: 4px;
                    color: var(--primary-color);
                }
                
                .attachment-menu-item span {
                    font-size: 12px;
                }
            `;
            document.head.appendChild(style);
            
            // Добавляем обработчики для элементов меню
            const items = fileMenu.querySelectorAll('.attachment-menu-item');
            items.forEach(item => {
                item.addEventListener('click', () => {
                    const type = item.getAttribute('data-type');
                    this.handleAttachmentSelection(type);
                    fileMenu.classList.remove('show');
                });
            });
            
            // Закрытие меню при клике вне его
            document.addEventListener('click', (e) => {
                if (!e.target.closest('#fileAttachmentMenu') && 
                    !e.target.closest('#fileBtn') && 
                    fileMenu.classList.contains('show')) {
                    fileMenu.classList.remove('show');
                }
            });
        }
        
        // Позиционируем меню над кнопкой файла
        const fileBtn = this.elements.fileBtn;
        const rect = fileBtn.getBoundingClientRect();
        fileMenu.style.left = `${rect.left}px`;
        
        // Показываем меню
        fileMenu.classList.add('show');
    },
    
    /**
     * Обработка выбора типа прикрепляемого файла
     * @param {string} type - Тип прикрепляемого файла
     */
    handleAttachmentSelection: function(type) {
        console.log(`Выбран тип прикрепления: ${type}`);
        
        // Создаем скрытый input для выбора файла
        const fileInput = document.createElement('input');
        fileInput.type = 'file';
        fileInput.style.display = 'none';
        
        // Устанавливаем принимаемые типы файлов в зависимости от выбранного типа
        switch (type) {
            case 'image':
                fileInput.accept = 'image/*';
                break;
            case 'video':
                fileInput.accept = 'video/*';
                break;
            case 'audio':
                fileInput.accept = 'audio/*';
                break;
            case 'document':
                fileInput.accept = '.pdf,.doc,.docx,.txt,.xls,.xlsx,.ppt,.pptx';
                break;
            default:
                fileInput.accept = '*/*';
        }
        
        // Добавляем в DOM
        document.body.appendChild(fileInput);
        
        // Программно вызываем клик
        fileInput.click();
        
        // Обработчик выбора файла
        fileInput.onchange = (e) => {
            if (e.target.files && e.target.files.length > 0) {
                const file = e.target.files[0];
                this.uploadFile(file);
            }
            
            // Удаляем input после использования
            document.body.removeChild(fileInput);
        };
    },

    /**
     * Формат размера файла
     * @param {number} bytes - Размер в байтах
     * @returns {string} Форматированный размер
     */
    formatFileSize: function(bytes) {
        if (bytes < 1024) {
            return bytes + ' байт';
        } else if (bytes < 1024 * 1024) {
            return (bytes / 1024).toFixed(1) + ' КБ';
        } else if (bytes < 1024 * 1024 * 1024) {
            return (bytes / (1024 * 1024)).toFixed(1) + ' МБ';
        } else {
            return (bytes / (1024 * 1024 * 1024)).toFixed(1) + ' ГБ';
        }
    },

    /**
     * Загрузка файла на сервер
     * @param {File} file - Файл для загрузки
     */
    uploadFile: function(file) {
        if (!file) return;
        
        console.log('Загрузка файла:', file.name);
        
        // Создаем объект FormData для отправки файла
        const formData = new FormData();
        formData.append('file', file);
        
        // Показываем индикатор загрузки
        const tempMessageId = 'upload-' + Date.now();
        const messageGroup = this.elements.messagesContainer.querySelector('.message-group:last-child');
        
        if (messageGroup) {
            const messageDiv = document.createElement('div');
            messageDiv.id = tempMessageId;
            messageDiv.className = 'message outgoing';
            messageDiv.innerHTML = `
                <div class="message-content">
                    <p class="message-text">Загрузка файла ${file.name}...</p>
                    <div class="message-meta">
                        <span class="message-time">${this.formatTime(new Date())}</span>
                        <span class="message-status"><i class="fas fa-circle-notch fa-spin"></i></span>
                    </div>
                </div>
            `;
            messageGroup.appendChild(messageDiv);
            this.scrollToBottom();
        }
        
        // Отправляем файл на сервер
        fetch('/upload', {
            method: 'POST',
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            // Удаляем временное сообщение
            const tempMessage = document.getElementById(tempMessageId);
            if (tempMessage) {
                tempMessage.remove();
            }
            
            if (data.success) {
                // Определяем тип файла по расширению
                const fileExtension = file.name.split('.').pop().toLowerCase();
                let fileType = 'document';
                
                if (['jpg', 'jpeg', 'png', 'gif', 'webp'].includes(fileExtension)) {
                    fileType = 'image';
                } else if (['mp4', 'webm', 'mkv', 'mov'].includes(fileExtension)) {
                    fileType = 'video';
                } else if (['mp3', 'wav', 'ogg', 'opus'].includes(fileExtension)) {
                    fileType = 'audio';
                }
                
                // Формируем и отправляем сообщение с файлом
                const fileUrl = data.file_url;
                const thumbnailUrl = data.thumbnail_url || fileUrl;
                
                // Создаем сообщение с файлом в формате: FILE:тип:url
                const fileMessage = `FILE:${fileType}:${fileUrl}`;
                
                // Отправляем сообщение с файлом через Socket.IO
                this.socket.emit('send_private_message', {
                    room: this.state.currentChatRoom,
                    receiver: this.state.currentChatPartner,
                    message: fileMessage
                });
                
                // Добавляем файловое сообщение в интерфейс
                const timestamp = Math.floor(Date.now() / 1000);
                const date = new Date(timestamp * 1000);
                const dateStr = this.formatDate(date);
                
                const message = {
                    sender: this.state.currentUser,
                    message: fileMessage,
                    timestamp: timestamp
                };
                
                // Группируем сообщение по дате
                const groupedMessages = {};
                if (!groupedMessages[dateStr]) {
                    groupedMessages[dateStr] = [];
                }
                groupedMessages[dateStr].push(message);
                
                // Отображаем сообщение
                this.renderMessageAppend(groupedMessages);
                this.scrollToBottom();
            } else {
                this.showError('Ошибка загрузки файла: ' + (data.error || 'Неизвестная ошибка'));
            }
        })
        .catch(error => {
            console.error('Ошибка загрузки файла:', error);
            
            // Удаляем временное сообщение
            const tempMessage = document.getElementById(tempMessageId);
            if (tempMessage) {
                tempMessage.remove();
            }
            
            this.showError('Ошибка загрузки файла: ' + error.message);
        });
    },

    /**
     * Переключение записи голосового сообщения
     */
    toggleVoiceRecording: function() {
        if (this.state.isRecording) {
            this.stopVoiceRecording();
        } else {
            this.startVoiceRecording();
        }
    },

    /**
     * Начало записи голосового сообщения
     */
    startVoiceRecording: function() {
        if (!this.state.currentChatRoom) {
            console.log('Нужно выбрать чат перед записью голосового сообщения');
            return;
        }
        
        console.log('Начало записи голосового сообщения');
        
        // Запрашиваем доступ к микрофону
        navigator.mediaDevices.getUserMedia({ audio: true })
            .then(stream => {
                // Создаем MediaRecorder
                this.state.mediaRecorder = new MediaRecorder(stream);
                this.state.recordedChunks = [];
                
                // Обработчик для данных записи
                this.state.mediaRecorder.ondataavailable = (e) => {
                    if (e.data.size > 0) {
                        this.state.recordedChunks.push(e.data);
                    }
                };
                
                // Обработчик окончания записи
                this.state.mediaRecorder.onstop = () => {
                    // Если запись была отменена, просто очищаем
                    if (!this.state.isRecording) {
                        this.state.recordedChunks = [];
                        return;
                    }
                    
                    // Создаем Blob из записанных данных
                    const audioBlob = new Blob(this.state.recordedChunks, { type: 'audio/webm' });
                    
                    // Создаем объект File из Blob
                    const audioFile = new File([audioBlob], "voice_message.webm", { 
                        type: 'audio/webm',
                        lastModified: Date.now()
                    });
                    
                    // Загружаем файл на сервер как голосовое сообщение
                    this.uploadVoiceMessage(audioFile);
                    
                    // Сбрасываем состояние записи
                    this.state.isRecording = false;
                    this.state.recordingStartTime = null;
                    this.state.recordedChunks = [];
                    
                    // Скрываем индикатор записи
                    this.elements.recordingIndicator.style.display = 'none';
                    this.elements.messageInput.style.display = 'block';
                };
                
                // Начинаем запись
                this.state.mediaRecorder.start();
                this.state.isRecording = true;
                this.state.recordingStartTime = Date.now();
                
                // Показываем индикатор записи
                this.elements.messageInput.style.display = 'none';
                this.elements.recordingIndicator.style.display = 'flex';
                
                // Обновляем таймер записи
                this.updateRecordingTimer();
            })
            .catch(error => {
                console.error('Ошибка при доступе к микрофону:', error);
                this.showError('Не удалось получить доступ к микрофону');
            });
    },

    /**
     * Обновление таймера записи
     */
    updateRecordingTimer: function() {
        if (!this.state.isRecording) return;
        
        const recordingTime = document.querySelector('.recording-time');
        const elapsed = Math.floor((Date.now() - this.state.recordingStartTime) / 1000);
        const minutes = Math.floor(elapsed / 60).toString().padStart(2, '0');
        const seconds = (elapsed % 60).toString().padStart(2, '0');
        
        recordingTime.textContent = `${minutes}:${seconds}`;
        
        // Обновляем таймер каждую секунду
        setTimeout(() => this.updateRecordingTimer(), 1000);
    },

    /**
     * Остановка записи голосового сообщения
     */
    stopVoiceRecording: function() {
        if (this.state.mediaRecorder && this.state.isRecording) {
            this.state.mediaRecorder.stop();
            
            // Останавливаем все треки медиапотока
            this.state.mediaRecorder.stream.getTracks().forEach(track => track.stop());
        }
    },

    /**
     * Отмена записи голосового сообщения
     */
    cancelVoiceRecording: function() {
        console.log('Отмена записи голосового сообщения');
        
        // Останавливаем запись, если она активна
        if (this.state.mediaRecorder && this.state.isRecording) {
            // Помечаем, что запись была отменена
            this.state.isRecording = false;
            
            // Останавливаем медиазапись
            this.state.mediaRecorder.stop();
            
            // Останавливаем все треки медиапотока
            this.state.mediaRecorder.stream.getTracks().forEach(track => track.stop());
        }
        
        // Сбрасываем состояние записи
        this.state.recordingStartTime = null;
        this.state.recordedChunks = [];
        
        // Скрываем индикатор записи и показываем поле ввода
        this.elements.recordingIndicator.style.display = 'none';
        this.elements.messageInput.style.display = 'block';
    },

    /**
     * Загрузка изображения
     */
    uploadImage: function() {
        // Создаем элемент input для выбора файла
        const fileInput = document.createElement('input');
        fileInput.type = 'file';
        fileInput.accept = 'image/*';
        fileInput.style.display = 'none';
        document.body.appendChild(fileInput);
        
        // Открываем диалог выбора файла
        fileInput.click();
        
        // Обработчик выбора файла
        fileInput.onchange = (e) => {
            if (e.target.files && e.target.files.length > 0) {
                const file = e.target.files[0];
                this.uploadFile(file);
            }
            
            // Удаляем временный элемент
            document.body.removeChild(fileInput);
        };
    },

    showError: function(message) {
        // Special handling for chat loading error
        if (message.includes('Не удалось загрузить список чатов')) {
            // Create or update persistent error banner
            let errorBanner = document.getElementById('chat-load-error-banner');
            
            if (!errorBanner) {
                errorBanner = document.createElement('div');
                errorBanner.id = 'chat-load-error-banner';
                errorBanner.className = 'chat-load-error-banner';
                errorBanner.innerHTML = `
                    <div class="error-banner-content">
                        <i class="fas fa-exclamation-triangle"></i>
                        <span>${message}</span>
                        <button class="reload-btn" onclick="location.reload()">
                            <i class="fas fa-sync-alt"></i> Обновить
                        </button>
                        <button class="close-btn">
                            <i class="fas fa-times"></i>
                        </button>
                    </div>
                `;
                
                // Add to DOM at the top of the page
                document.body.insertBefore(errorBanner, document.body.firstChild);
                
                // Add close button event listener
                const closeBtn = errorBanner.querySelector('.close-btn');
                closeBtn.addEventListener('click', () => {
                    document.body.removeChild(errorBanner);
                });
            } else {
                // Update existing banner
                const messageSpan = errorBanner.querySelector('span');
                if (messageSpan) {
                    messageSpan.textContent = message;
                }
            }
            
            // Also log to console
            console.error('Ошибка загрузки чатов:', message);
            return;
        }
        
        // Simple error notification for other errors
        console.error('Ошибка:', message);
        
        // Создаем элемент оповещения
        const errorToast = document.createElement('div');
        errorToast.className = 'error-toast';
        errorToast.innerHTML = `
            <div class="error-toast-content">
                <i class="fas fa-exclamation-circle"></i>
                <span>${message}</span>
            </div>
        `;
        
        // Добавляем в DOM
        document.body.appendChild(errorToast);
        
        // Показываем с анимацией
        setTimeout(() => {
            errorToast.classList.add('show');
        }, 10);
        
        // Автоматически скрываем через 3 секунды
        setTimeout(() => {
            errorToast.classList.remove('show');
            setTimeout(() => {
                document.body.removeChild(errorToast);
            }, 300);
        }, 3000);
    },

    /**
     * Рендерит сообщение
     * @param {Object} message - Объект сообщения
     * @returns {HTMLElement} - DOM-элемент сообщения
     */
    renderMessage: function(message) {
        // Создаем элемент сообщения
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message';
        messageDiv.classList.add(message.sender === this.state.currentUser ? 'outgoing' : 'incoming');
        
        // Добавляем уникальный ID сообщения для возможности обновления статуса
        messageDiv.id = `message-${message.id}`;
        messageDiv.setAttribute('data-message-id', message.id);
        
        // Определяем статус сообщения
        let statusIcon = '<i class="fas fa-check"></i>'; // По умолчанию - отправлено
        
        // Если сообщение от нас и есть информация о прочтении
        if (message.sender === this.state.currentUser && message.read) {
            statusIcon = '<i class="fas fa-check-double" style="color: var(--success-color);"></i>'; // Прочитано
        }
        
        // Проверяем, является ли сообщение файловым
        if (message.message.startsWith('FILE:')) {
            const parts = message.message.split(':');
            if (parts.length >= 3) {
                const fileType = parts[1];
                const fileUrl = parts[2];
                messageDiv.innerHTML = this.renderFileMessage(fileType, fileUrl);
                
                // Добавляем статус к файловому сообщению
                const metaDiv = messageDiv.querySelector('.message-meta');
                if (metaDiv) {
                    const statusSpan = document.createElement('span');
                    statusSpan.className = 'message-status';
                    statusSpan.innerHTML = statusIcon;
                    metaDiv.appendChild(statusSpan);
                }
            } else {
                // Обрабатываем некорректный формат файла
                messageDiv.innerHTML = `
                    <div class="message-content">
                        <p class="message-text">Некорректный формат файла</p>
                        <div class="message-meta">
                            <span class="message-time">${this.formatTime(new Date(message.timestamp * 1000))}</span>
                            <span class="message-status">${statusIcon}</span>
                        </div>
                    </div>
                `;
            }
        } else {
            // Обрабатываем обычное текстовое сообщение
            messageDiv.innerHTML = `
                <div class="message-content">
                    <p class="message-text">${this.formatMessageText(message.message)}</p>
                    <div class="message-meta">
                        <span class="message-time">${this.formatTime(new Date(message.timestamp * 1000))}</span>
                        <span class="message-status">${statusIcon}</span>
                    </div>
                </div>
            `;
        }
        
        // Добавляем анимацию появления сообщения
        setTimeout(() => {
            messageDiv.classList.add('message-appear');
            
            // Инициализируем аудио элементы после добавления в DOM
            this.initAudioElements();
        }, 50);
        
        return messageDiv;
    },

    /**
     * Форматирует текст сообщения (обрабатывает ссылки, emoji и т.д.)
     * @param {string} text - Текст сообщения
     * @returns {string} - Отформатированный текст
     */
    formatMessageText: function(text) {
        if (!text) return '';
        
        // Экранируем HTML-теги
        let formatted = text
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
        
        // Заменяем URL на кликабельные ссылки
        const urlRegex = /(https?:\/\/[^\s]+)/g;
        formatted = formatted.replace(urlRegex, '<a href="$1" target="_blank">$1</a>');
        
        // Заменяем переносы строк на <br>
        formatted = formatted.replace(/\n/g, '<br>');
        
        return formatted;
    },

    /**
     * Обрабатывает входящее сообщение от сервера
     * @param {Object} data Данные сообщения
     */
    handleIncomingMessage: function(data) {
        try {
            // Подробное логирование для отладки
            console.log('🔵 Получено новое сообщение:', data);
            
            // Проверка наличия данных
            if (!data) {
                this.handleSilentError('Получены пустые данные сообщения');
                return;
            }
            
            // Структурируем объект сообщения для обеспечения совместимости
            const message = {
                id: data.id || `server-${Date.now()}`,
                sender: data.sender,
                recipient: data.recipient,
                message: data.message,
                timestamp: data.timestamp || Math.floor(Date.now() / 1000),
                room: data.room
            };
            
            console.log(`🔍 Проверка сообщения: sender=${message.sender}, recipient=${message.recipient}, room=${message.room || 'отсутствует'}`);
            
            // Записываем чат, к которому относится сообщение
            let messageRoom = message.room;
            
            // Если комнаты нет в сообщении, определяем ее по отправителю и получателю
            if (!messageRoom) {
                const participants = [message.sender, message.recipient].sort();
                messageRoom = participants.join('_');
                console.log(`📝 Комната не указана в сообщении, вычисляем: ${messageRoom}`);
            }
            
            // Определяем, принадлежит ли сообщение текущему чату
            const isCurrentChat = this.isMessageForCurrentChat(message);
            console.log(`🧩 Принадлежит текущему чату: ${isCurrentChat} (текущая комната: ${this.state.currentChatRoom || 'нет'}, собеседник: ${this.state.currentChatPartner || 'нет'})`);
            
            // Если сообщение для текущего чата, отображаем его
            if (isCurrentChat) {
                // Проверяем, есть ли уже это сообщение в DOM (по id)
                const existingMsg = document.querySelector(`[data-message-id="${message.id}"]`);
                
                // Проверяем, есть ли временное сообщение от этого же отправителя
                const tempMessages = document.querySelectorAll(`[data-message-id^="temp-"]`);
                let tempMessage = null;
                
                // Если сообщение от текущего пользователя, проверяем, не является ли оно подтверждением отправленного
                if (message.sender === this.state.currentUser) {
                    for (let i = 0; i < tempMessages.length; i++) {
                        const tempElement = tempMessages[i];
                        const tempContent = tempElement.querySelector('.message-text').textContent;
                        
                        if (tempContent === message.message) {
                            tempMessage = tempElement;
                            console.log('🔄 Найдено временное сообщение для замены:', tempContent);
                            break;
                        }
                    }
                }
                
                // Если есть временное сообщение, заменяем его на постоянное
                if (tempMessage) {
                    tempMessage.setAttribute('data-message-id', message.id);
                    
                    // Обновляем статус сообщения
                    const statusIcon = tempMessage.querySelector('.message-status');
                    if (statusIcon) {
                        statusIcon.innerHTML = '<i class="fas fa-check"></i>';
                        statusIcon.title = 'Доставлено';
                    }
                    
                    console.log('✅ Временное сообщение заменено на постоянное с ID:', message.id);
                } 
                // Если сообщение еще не существует, добавляем его
                else if (!existingMsg) {
                    console.log('➕ Добавляем новое сообщение в чат:', message.message);
                    
                    try {
                        // Рендерим сообщение
                        const messageElement = this.renderMessage(message);
                        
                        // Находим или создаем группу сообщений для текущей даты
                        const dateStr = this.formatDate(new Date(message.timestamp * 1000));
                        let dateGroup = null;
                        let messageGroup = null;
                        
                        // Ищем группу с этой датой
                        const dateDivs = this.elements.messagesContainer.querySelectorAll('.message-date');
                        for (let i = 0; i < dateDivs.length; i++) {
                            if (dateDivs[i].textContent.trim() === dateStr) {
                                dateGroup = dateDivs[i];
                                messageGroup = dateGroup.nextElementSibling;
                                
                                if (messageGroup && messageGroup.classList.contains('message-group')) {
                                    break;
                                } else {
                                    dateGroup = null; // Сбрасываем, если следующий элемент не группа
                                }
                            }
                        }
                        
                        // Если не нашли группу, создаем новую
                        if (!dateGroup) {
                            // Удаляем сообщение о пустом чате, если оно есть
                            const emptyMessage = this.elements.messagesContainer.querySelector('.empty-chat-message');
                            if (emptyMessage) {
                                emptyMessage.remove();
                            }
                            
                            // Удаляем приветственный экран, если он есть
                            const welcomeScreen = this.elements.messagesContainer.querySelector('.welcome-screen');
                            if (welcomeScreen) {
                                welcomeScreen.remove();
                            }
                            
                            // Создаем разделитель с датой
                            dateGroup = document.createElement('div');
                            dateGroup.className = 'message-date';
                            dateGroup.innerHTML = `<span>${dateStr}</span>`;
                            this.elements.messagesContainer.appendChild(dateGroup);
                            
                            // Создаем группу сообщений
                            messageGroup = document.createElement('div');
                            messageGroup.className = 'message-group';
                            this.elements.messagesContainer.appendChild(messageGroup);
                        }
                        
                        // Добавляем сообщение в группу
                        messageGroup.appendChild(messageElement);
                        
                        // Прокручиваем к последнему сообщению
                        this.scrollToBottom();
                        
                        // Если сообщение от собеседника, обрабатываем уведомления
                        if (message.sender !== this.state.currentUser) {
                            console.log(`🔔 Обрабатываем сообщение от ${message.sender}`);
                            
                            // Воспроизводим звук уведомления
                            if (this.elements.notificationSound) {
                                this.elements.notificationSound.play().catch(error => {
                                    console.log('Не удалось воспроизвести звук уведомления:', error);
                                });
                            }
                            
                            // Отмечаем сообщение как прочитанное, так как мы в чате
                            this.socket.emit('read_message', {
                                room: this.state.currentChatRoom,
                                message_id: message.id
                            });
                        }
                    } catch (innerError) {
                        this.handleSilentError('Ошибка при добавлении сообщения в DOM', innerError);
                    }
                } else {
                    console.log('⏭️ Сообщение уже существует в DOM, пропускаем:', message.id);
                }
            } else {
                // Сообщение для другого чата или от другого пользователя
                console.log(`📢 Сообщение для другого чата: ${message.room || 'неизвестная комната'}`);
                
                // Если сообщение не от текущего пользователя
                if (message.sender !== this.state.currentUser) {
                    console.log(`🔔 Обрабатываем непрочитанное сообщение от ${message.sender}`);
                    
                    // Добавляем сообщение в кэш непрочитанных
                    this.addUnreadMessage(message);
                    
                    // Обновляем счетчики и индикаторы
                    this.updateUnreadCount(message.sender);
                    
                    // Воспроизводим звук уведомления
                    if (this.elements.notificationSound) {
                        this.elements.notificationSound.play().catch(error => {
                            console.log('Не удалось воспроизвести звук уведомления:', error);
                        });
                    }
                    
                    // Показываем браузерное уведомление, если разрешено
                    if (this.settings.enableNotifications && Notification.permission === 'granted') {
                        let messageText = message.message;
                        
                        // Форматируем текст для файловых сообщений
                        if (messageText.startsWith('FILE:')) {
                            const parts = messageText.split(':');
                            if (parts.length >= 2) {
                                const fileType = parts[1];
                                switch (fileType) {
                                    case 'image': messageText = 'Фото'; break;
                                    case 'video': messageText = 'Видео'; break;
                                    case 'audio': messageText = 'Аудио'; break;
                                    case 'voice': messageText = 'Голосовое сообщение'; break;
                                    case 'document': messageText = 'Документ'; break;
                                    default: messageText = 'Файл';
                                }
                            }
                        }
                        
                        // Создаем и показываем уведомление
                        const notification = new Notification(`Сообщение от ${message.sender}`, {
                            body: messageText,
                            icon: '/static/img/logo.png'
                        });
                        
                        // Обработчик клика по уведомлению (открываем чат)
                        notification.onclick = () => {
                            // Сортируем имена для правильного формирования ID комнаты
                            const chatMembers = [this.state.currentUser, message.sender].sort();
                            const roomId = `private_${chatMembers.join('_')}`;
                            this.openChat(roomId, 'private', message.sender);
                            window.focus();
                            notification.close();
                        };
                    }
                    
                    // Обновляем список чатов для отображения нового сообщения
                    this.updateChatListWithMessage(message);
                }
            }
        } catch (error) {
            this.handleSilentError('Ошибка при обработке входящего сообщения', error);
        }
    },

    /**
     * Проверяет, относится ли сообщение к текущему чату
     * @param {Object} message Объект сообщения
     * @returns {Boolean} Относится ли сообщение к текущему чату
     */
    isMessageForCurrentChat: function(message) {
        // Если нет текущего чата, сообщение не для текущего чата
        if (!this.state.currentChatPartner || !this.state.currentChatRoom) {
            return false;
        }
        
        // Если в сообщении указана комната и она совпадает с текущей
        if (message.room && this.state.currentChatRoom === message.room) {
            return true;
        }
        
        // Если комнаты нет, проверяем по отправителю и получателю
        const participants = [message.sender, message.recipient].sort();
        const computedRoom = participants.join('_');
        
        return computedRoom === this.state.currentChatRoom;
    },

    /**
     * Добавляет сообщение в список непрочитанных
     * @param {Object} message Объект сообщения
     */
    addUnreadMessage: function(message) {
        // Определяем, от кого сообщение
        const sender = message.sender;
        
        // Если отправитель - текущий пользователь, не считаем непрочитанным
        if (sender === this.state.currentUser) {
            return;
        }
        
        // Инициализируем объект непрочитанных сообщений, если его нет
        if (!this.state.unreadMessages) {
            this.state.unreadMessages = {};
        }
        
        // Добавляем сообщение в список непрочитанных для этого отправителя
        if (!this.state.unreadMessages[sender]) {
            this.state.unreadMessages[sender] = [];
        }
        
        // Проверяем, нет ли уже такого сообщения
        const isDuplicate = this.state.unreadMessages[sender].some(msg => msg.id === message.id);
        
        if (!isDuplicate) {
            this.state.unreadMessages[sender].push(message);
            
            // Обновляем счетчик непрочитанных сообщений в UI
            this.updateUnreadCount(sender);
        }
    },

    /**
     * Останавливает индикатор набора текста
     */
    stopTyping: function() {
        try {
            // Проверяем, что socket существует и подключен
            if (this.socket && this.socket.connected && this.state.currentChatRoom) {
                // Отправляем событие о прекращении набора
                this.socket.emit('stop typing', {
                    room: this.state.currentChatRoom
                });
                console.log('Отправлено событие stop typing');
            }
        } catch (error) {
            this.handleSilentError('Ошибка при отправке события прекращения набора', error);
        }
    },

    /**
     * Обновляет данные в списке чатов после получения нового сообщения
     * @param {Object} message - Объект сообщения
     */
    updateChatListWithMessage: function(message) {
        // Проверяем наличие данных сообщения
        if (!message || !message.sender || !message.message) {
            return;
        }

        // Определяем ID чата и партнера
        const chatPartner = message.sender === this.state.currentUser ? message.recipient : message.sender;
        const chatId = `private_${message.sender}_${message.recipient}`;
        const alternativeChatId = `private_${message.recipient}_${message.sender}`;

        // Находим чат в списке
        let chatIndex = this.state.chats.findIndex(c => 
            c.id === chatId || c.id === alternativeChatId || 
            (c.type === 'private' && c.partner === chatPartner)
        );

        // Форматируем текст последнего сообщения для отображения в списке чатов
        let displayText = message.message;
        
        // Если это файл, меняем отображение на более понятное
        if (message.message.startsWith('FILE:')) {
            const parts = message.message.split(':');
            const fileType = parts[1];
            
            // Выбираем текст в зависимости от типа файла
            switch (fileType) {
                case 'image':
                    displayText = 'Фото';
                    break;
                case 'video':
                    displayText = 'Видео';
                    break;
                case 'audio':
                    displayText = 'Аудио';
                    break;
                case 'voice':
                    displayText = 'Голосовое сообщение';
                    break;
                case 'document':
                    displayText = 'Документ';
                    break;
                default:
                    displayText = 'Файл';
            }
        } else {
            // Ограничиваем длину текстового сообщения
            if (displayText.length > 30) {
                displayText = displayText.substring(0, 27) + '...';
            }
        }

        // Если чат найден, обновляем его данные
        if (chatIndex !== -1) {
            const chat = this.state.chats[chatIndex];
            
            // Обновляем последнее сообщение
            chat.last_message = {
                text: displayText,
                timestamp: message.timestamp,
                sender: message.sender
            };
            
            // Увеличиваем счетчик непрочитанных, если сообщение от другого пользователя
            // и это не текущий активный чат
            if (message.sender !== this.state.currentUser && 
                (!this.state.currentChatRoom || this.state.currentChatRoom !== chat.id)) {
                chat.unread_count = (chat.unread_count || 0) + 1;
            }
            
            // Удаляем чат с текущей позиции
            this.state.chats.splice(chatIndex, 1);
            
            // Добавляем его в начало списка (самый свежий)
            this.state.chats.unshift(chat);
        } else {
            // Если чат не найден, создаем новый
            const newChat = {
                id: chatId,
                type: 'private',
                partner: chatPartner,
                name: chatPartner,
                last_message: {
                    text: displayText,
                    timestamp: message.timestamp,
                    sender: message.sender
                },
                unread_count: message.sender !== this.state.currentUser ? 1 : 0,
                is_favorite: false
            };
            
            // Добавляем новый чат в начало списка
            this.state.chats.unshift(newChat);
        }
        
        // Перерисовываем список чатов для отображения изменений
        this.renderChatList();
    },

    /**
     * Инициализация аудио элементов после рендеринга
     */
    initAudioElements: function() {
        if (this.pendingAudioInitializations && this.pendingAudioInitializations.length > 0) {
            this.pendingAudioInitializations.forEach(item => {
                try {
                    item.setup();
                } catch (e) {
                    console.error('Ошибка при инициализации аудио:', e);
                }
            });
            // Очищаем список после обработки
            this.pendingAudioInitializations = [];
        }
    },

    /**
     * Обновляет счетчик непрочитанных сообщений для указанного пользователя
     * @param {string} username - Имя пользователя
     */
    updateUnreadCount: function(username) {
        if (!username) return;
        
        console.log(`Обновление счетчика непрочитанных для ${username}`);
        
        // Находим чаты, связанные с этим пользователем
        const userChats = this.state.chats.filter(chat => {
            // Для приватных чатов
            if (!chat.id.includes('group_')) {
                return chat.id.includes(username) || chat.partner === username;
            }
            return false;
        });
        
        // Если нашли чаты, обновляем в них счетчик непрочитанных
        userChats.forEach(chat => {
            // Если есть непрочитанные сообщения для этого пользователя
            const unreadCount = this.state.unreadMessages && this.state.unreadMessages[username] 
                ? this.state.unreadMessages[username].length 
                : 0;
            
            // Обновляем счетчик в объекте чата
            chat.unread_count = unreadCount;
            
            // Находим элемент этого чата в DOM и обновляем счетчик
            const chatElement = document.querySelector(`[data-chat-id="${chat.id}"]`);
            if (chatElement) {
                // Обновляем счетчик непрочитанных
                const badge = chatElement.querySelector('.unread-badge');
                if (badge) {
                    if (unreadCount > 0) {
                        badge.textContent = unreadCount;
                        badge.style.display = 'flex';
                    } else {
                        badge.style.display = 'none';
                    }
                } else if (unreadCount > 0) {
                    // Если бейджа нет, но есть непрочитанные, создаем его
                    const badges = chatElement.querySelector('.chat-item-badges');
                    if (badges) {
                        const newBadge = document.createElement('span');
                        newBadge.className = 'unread-badge';
                        newBadge.textContent = unreadCount;
                        badges.prepend(newBadge);
                    }
                }
                
                // Добавляем класс для выделения чата с новыми сообщениями
                if (unreadCount > 0) {
                    chatElement.classList.add('new-message');
                } else {
                    chatElement.classList.remove('new-message');
                }
            }
        });
    },

    /**
     * Отмечает все сообщения в текущем чате как прочитанные
     */
    markAsRead: function() {
        if (!this.state.currentChatPartner) return;
        
        console.log(`Отмечаем сообщения от ${this.state.currentChatPartner} как прочитанные`);
        
        // Отправляем запрос на сервер через REST API для надежности
        fetch('/api/mark_messages_read', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                sender: this.state.currentChatPartner
            })
        })
        .then(response => response.json())
        .then(data => {
            console.log('API ответ mark_messages_read:', data);
            
            if (data.success) {
                // Очищаем непрочитанные сообщения для текущего собеседника
                if (this.state.unreadMessages && this.state.unreadMessages[this.state.currentChatPartner]) {
                    // Отправляем на сервер подтверждение о прочтении для каждого сообщения
                    this.state.unreadMessages[this.state.currentChatPartner].forEach(message => {
                        this.socket.emit('read_message', {
                            room: this.state.currentChatRoom,
                            message_id: message.id
                        });
                    });
                    
                    // Очищаем список непрочитанных сообщений
                    this.state.unreadMessages[this.state.currentChatPartner] = [];
                    
                    // Находим чат и обновляем счетчик непрочитанных сообщений
                    this.state.chats.forEach(chat => {
                        if (chat.id.includes(this.state.currentChatPartner) || 
                            chat.partner === this.state.currentChatPartner) {
                            chat.unread_count = 0;
                        }
                    });
                    
                    // Обновляем пользовательский интерфейс
                    this.updateUnreadCount(this.state.currentChatPartner);
                    
                    // Обновляем список чатов
                    this.renderChatList();
                    
                    // Записываем в консоль для отладки
                    console.log(`Счетчик непрочитанных сообщений для ${this.state.currentChatPartner} сброшен`);
                }
            } else {
                console.error('Ошибка при отметке сообщений как прочитанные:', data.error);
            }
        })
        .catch(error => {
            console.error('Ошибка при отметке сообщений как прочитанные:', error);
        });
    },
    
    /**
     * Обновляет статус непрочитанных сообщений
     * @param {Object} message - Объект сообщения
     */
    updateUnreadStatus: function(message) {
        // Если сообщение от текущего собеседника, отмечаем как прочитанное
        if (message.sender === this.state.currentChatPartner) {
            // Отправляем подтверждение прочтения
            this.socket.emit('read_message', {
                room: this.state.currentChatRoom,
                message_id: message.id
            });
        } else {
            // Добавляем к непрочитанным
            this.addUnreadMessage(message);
            // Обновляем интерфейс
            this.updateUnreadCount(message.sender);
        }
    },

    /**
     * Загружает голосовое сообщение на сервер
     * @param {File} file - Файл с голосовым сообщением
     */
    uploadVoiceMessage: function(file) {
        if (!file) return;
        
        console.log('Загрузка голосового сообщения:', file.name);
        
        // Создаем объект FormData для отправки файла
        const formData = new FormData();
        formData.append('file', file);
        formData.append('type', 'voice'); // Указываем тип файла как голосовое сообщение
        
        // Показываем индикатор загрузки
        const tempMessageId = 'upload-' + Date.now();
        const messageGroup = this.elements.messagesContainer.querySelector('.message-group:last-child');
        
        if (messageGroup) {
            const messageDiv = document.createElement('div');
            messageDiv.id = tempMessageId;
            messageDiv.className = 'message outgoing';
            messageDiv.innerHTML = `
                <div class="message-content">
                    <p class="message-text">Отправка голосового сообщения...</p>
                    <div class="message-meta">
                        <span class="message-time">${this.formatTime(new Date())}</span>
                        <span class="message-status"><i class="fas fa-circle-notch fa-spin"></i></span>
                    </div>
                </div>
            `;
            messageGroup.appendChild(messageDiv);
            this.scrollToBottom();
        }
        
        // Отправляем файл на сервер
        fetch('/upload', {
            method: 'POST',
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            // Удаляем временное сообщение
            const tempMessage = document.getElementById(tempMessageId);
            if (tempMessage) {
                tempMessage.remove();
            }
            
            if (data.success) {
                // Формируем и отправляем сообщение с голосовым файлом
                const fileUrl = data.file_url;
                
                // Создаем сообщение с голосовым файлом в формате: FILE:voice:url
                const fileMessage = `FILE:voice:${fileUrl}`;
                
                // Отправляем сообщение с файлом через Socket.IO
                this.socket.emit('send_private_message', {
                    room: this.state.currentChatRoom,
                    receiver: this.state.currentChatPartner,
                    message: fileMessage
                });
                
                // Добавляем файловое сообщение в интерфейс
                const timestamp = Math.floor(Date.now() / 1000);
                const date = new Date(timestamp * 1000);
                const dateStr = this.formatDate(date);
                
                const message = {
                    sender: this.state.currentUser,
                    message: fileMessage,
                    timestamp: timestamp
                };
                
                // Группируем сообщение по дате
                const groupedMessages = {};
                if (!groupedMessages[dateStr]) {
                    groupedMessages[dateStr] = [];
                }
                groupedMessages[dateStr].push(message);
                
                // Отображаем сообщение
                this.renderMessageAppend(groupedMessages);
                this.scrollToBottom();
            } else {
                this.showError('Ошибка загрузки голосового сообщения: ' + (data.error || 'Неизвестная ошибка'));
            }
        })
        .catch(error => {
            console.error('Ошибка загрузки голосового сообщения:', error);
            
            // Удаляем временное сообщение
            const tempMessage = document.getElementById(tempMessageId);
            if (tempMessage) {
                tempMessage.remove();
            }
            
            this.showError('Ошибка загрузки голосового сообщения: ' + error.message);
        });
    },

    /**
     * Инициализация звукового уведомления
     */
    setupNotificationSound: function() {
        // Создаем элемент аудио для уведомлений
        this.elements.notificationSound = document.createElement('audio');
        this.elements.notificationSound.src = '/static/sounds/notification.mp3';
        this.elements.notificationSound.preload = 'auto';
        
        // Добавляем в DOM, но скрываем
        this.elements.notificationSound.style.display = 'none';
        document.body.appendChild(this.elements.notificationSound);
        
        console.log('Звуковое уведомление инициализировано');
    },

    /**
     * Запрос разрешения на браузерные уведомления
     */
    requestNotificationPermission: function() {
        // Проверяем поддержку уведомлений в браузере
        if (!('Notification' in window)) {
            console.log('Этот браузер не поддерживает уведомления');
            return;
        }
        
        // Если разрешение еще не запрошено, запрашиваем
        if (Notification.permission !== 'granted' && Notification.permission !== 'denied') {
            Notification.requestPermission().then(permission => {
                if (permission === 'granted') {
                    console.log('Разрешение на уведомления получено');
                }
            });
        }
    },

    /**
     * Отметить все сообщения как прочитанные
     */
    markAllAsRead: function() {
        console.log('Отмечаем все сообщения как прочитанные');
        
        // Если нет непрочитанных сообщений или чатов, просто выходим
        if (!this.state.unreadMessages || Object.keys(this.state.unreadMessages).length === 0) {
            return;
        }
        
        // Сохраняем все собеседников, у которых есть непрочитанные сообщения
        const senders = Object.keys(this.state.unreadMessages);
        let processedSenders = 0;
        
        // Для каждого отправителя делаем отдельный вызов API
        senders.forEach(sender => {
            // Отправляем запрос на сервер через REST API
            fetch('/api/mark_messages_read', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    sender: sender
                })
            })
            .then(response => response.json())
            .then(data => {
                processedSenders++;
                console.log(`API ответ mark_messages_read для ${sender}:`, data);
                
                // После обработки всех запросов обновляем UI
                if (processedSenders === senders.length) {
                    this.updateUIAfterMarkAllAsRead();
                }
            })
            .catch(error => {
                processedSenders++;
                console.error(`Ошибка при отметке сообщений от ${sender} как прочитанные:`, error);
                
                // После обработки всех запросов обновляем UI
                if (processedSenders === senders.length) {
                    this.updateUIAfterMarkAllAsRead();
                }
            });
            
            // Дополнительно отправляем Socket.IO события для каждого сообщения
            this.state.unreadMessages[sender].forEach(message => {
                // Формируем ID комнаты для этого пользователя
                const chatMembers = [this.state.currentUser, sender].sort();
                const roomId = `private_${chatMembers.join('_')}`;
                
                this.socket.emit('read_message', {
                    room: roomId,
                    message_id: message.id
                });
            });
        });
    },
    
    /**
     * Обновляет интерфейс после отметки всех сообщений как прочитанных
     */
    updateUIAfterMarkAllAsRead: function() {
        // Очищаем списки непрочитанных сообщений
        for (const username in this.state.unreadMessages) {
            this.state.unreadMessages[username] = [];
        }
        
        // Обновляем счетчики в чатах
        this.state.chats.forEach(chat => {
            chat.unread_count = 0;
        });
        
        // Обновляем отображение списка чатов
        this.renderChatList();
        
        // Показываем уведомление об успешном прочтении
        this.showToast('Все сообщения отмечены как прочитанные');
    },
    
    /**
     * Показать уведомление-тост
     * @param {string} message - Текст уведомления
     * @param {string} type - Тип уведомления (success, error, info)
     */
    showToast: function(message, type = 'success') {
        // Проверяем, существует ли уже контейнер для тостов
        let toastContainer = document.querySelector('.toast-container');
        if (!toastContainer) {
            toastContainer = document.createElement('div');
            toastContainer.className = 'toast-container';
            document.body.appendChild(toastContainer);
            
            // Добавляем базовые стили для контейнера тостов, если их еще нет
            if (!document.getElementById('toast-styles')) {
                const style = document.createElement('style');
                style.id = 'toast-styles';
                style.textContent = `
                    .toast-container {
                        position: fixed;
                        bottom: 20px;
                        right: 20px;
                        z-index: 9999;
                        display: flex;
                        flex-direction: column;
                        gap: 10px;
                    }
                    .toast {
                        padding: 12px 16px;
                        border-radius: 8px;
                        font-size: 14px;
                        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
                        display: flex;
                        align-items: center;
                        min-width: 250px;
                        max-width: 350px;
                        overflow: hidden;
                        color: white;
                        animation: toast-in 0.3s ease forwards;
                    }
                    .toast i {
                        margin-right: 10px;
                        font-size: 16px;
                    }
                    .toast.success {
                        background-color: var(--success-color);
                    }
                    .toast.error {
                        background-color: var(--danger-color);
                    }
                    .toast.info {
                        background-color: var(--info-color);
                    }
                    @keyframes toast-in {
                        from {
                            transform: translateX(100%);
                            opacity: 0;
                        }
                        to {
                            transform: translateX(0);
                            opacity: 1;
                        }
                    }
                `;
                document.head.appendChild(style);
            }
        }
        
        // Создаем элемент тоста
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        
        // Выбираем иконку в зависимости от типа уведомления
        let icon = 'info-circle';
        if (type === 'success') icon = 'check-circle';
        if (type === 'error') icon = 'exclamation-circle';
        
        toast.innerHTML = `<i class="fas fa-${icon}"></i> ${message}`;
        
        // Добавляем тост в контейнер
        toastContainer.appendChild(toast);
        
        // Удаляем тост через 3 секунды
        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateX(100%)';
            toast.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
            
            setTimeout(() => {
                if (toast.parentNode) {
                    toast.parentNode.removeChild(toast);
                }
            }, 300);
        }, 3000);
    },

    /**
     * Обновляет статус прочтения сообщения в интерфейсе
     * @param {string} messageId - ID сообщения
     * @param {string} readBy - Имя пользователя, прочитавшего сообщение
     */
    updateMessageReadStatus: function(messageId, readBy) {
        // Находим элемент сообщения
        const messageElement = document.getElementById(`message-${messageId}`);
        if (!messageElement) return;
        
        // Находим элемент статуса сообщения
        const statusElement = messageElement.querySelector('.message-status');
        if (!statusElement) return;
        
        // Обновляем иконку статуса на "прочитано"
        statusElement.innerHTML = '<i class="fas fa-check-double" style="color: var(--success-color);"></i>';
        
        // Добавляем всплывающую подсказку с информацией о прочтении
        const timestamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        statusElement.setAttribute('title', `Прочитано ${readBy} в ${timestamp}`);
        
        // Очищаем это сообщение из списка непрочитанных, если оно там есть
        if (this.state.unreadMessages) {
            for (const username in this.state.unreadMessages) {
                const index = this.state.unreadMessages[username].findIndex(msg => msg.id === messageId);
                if (index !== -1) {
                    this.state.unreadMessages[username].splice(index, 1);
                }
            }
        }
    },

    /**
     * Обновляет данные чата при получении события chat_update
     * @param {Object} data - Данные чата для обновления
     */
    updateChatData: function(data) {
        console.log('Обновление данных чата:', data);
        
        if (!data || !data.id) {
            console.error('Неверные данные для обновления чата');
            return;
        }
        
        // Найдем чат в списке по его ID
        const chatIndex = this.state.chats.findIndex(chat => chat.id === data.id);
        
        if (chatIndex !== -1) {
            // Обновляем существующий чат
            if (data.unread_count !== undefined) {
                this.state.chats[chatIndex].unread_count = data.unread_count;
            }
            
            if (data.last_message) {
                this.state.chats[chatIndex].last_message = data.last_message;
            }
            
            if (data.partner) {
                this.state.chats[chatIndex].partner = data.partner;
            }
            
            // Если это текущий открытый чат, обнуляем счетчик непрочитанных
            if (this.state.currentChatPartner && 
                (this.state.chats[chatIndex].id.includes(this.state.currentChatPartner) || 
                 this.state.chats[chatIndex].partner === this.state.currentChatPartner)) {
                this.state.chats[chatIndex].unread_count = 0;
            }
            
            // Обновляем UI
            this.renderChatList();
        } else if (data.partner) {
            // Если чата нет в списке, добавляем его
            const newChat = {
                id: data.id,
                partner: data.partner,
                unread_count: data.unread_count || 0,
                last_message: data.last_message || { text: '', timestamp: Date.now() / 1000 }
            };
            
            this.state.chats.push(newChat);
            this.renderChatList();
        }
    },

    /**
     * Инициализация обработчиков контекстного меню для сообщений
     */
    setupMessageContextMenu: function() {
        // Создаем контекстное меню для сообщений, если его еще нет
        if (!document.getElementById('messageContextMenu')) {
            const contextMenu = document.createElement('ul');
            contextMenu.id = 'messageContextMenu';
            contextMenu.className = 'context-menu';
            contextMenu.innerHTML = `
                <li data-action="copy"><i class="fas fa-copy"></i> Копировать текст</li>
                <li data-action="reply"><i class="fas fa-reply"></i> Ответить</li>
                <li data-action="forward"><i class="fas fa-share"></i> Переслать</li>
                <li data-action="delete"><i class="fas fa-trash"></i> Удалить</li>
                <li data-action="compression"><i class="fas fa-compress-alt"></i> Информация о сжатии</li>
            `;
            document.body.appendChild(contextMenu);
            
            // Добавляем обработчики кликов по пунктам меню
            contextMenu.addEventListener('click', (e) => {
                const action = e.target.closest('li')?.dataset.action;
                const messageId = contextMenu.dataset.messageId;
                
                if (!action || !messageId) return;
                
                switch (action) {
                    case 'copy':
                        this.copyMessageText(messageId);
                        break;
                    case 'reply':
                        this.replyToMessage(messageId);
                        break;
                    case 'forward':
                        this.forwardMessage(messageId);
                        break;
                    case 'delete':
                        this.deleteMessage(messageId);
                        break;
                    case 'compression':
                        this.showMessageCompressionInfo(messageId);
                        break;
                }
                
                // Закрываем меню после выбора действия
                contextMenu.style.display = 'none';
            });
        }
        
        // Предотвращаем стандартное контекстное меню браузера и показываем наше
        this.elements.messagesContainer.addEventListener('contextmenu', (e) => {
            e.preventDefault();
            
            // Находим ближайший элемент сообщения
            const messageEl = e.target.closest('.message');
            if (!messageEl) return;
            
            const messageId = messageEl.getAttribute('data-message-id');
            if (!messageId) return;
            
            // Позиционируем и показываем контекстное меню
            const contextMenu = document.getElementById('messageContextMenu');
            contextMenu.dataset.messageId = messageId;
            contextMenu.style.top = `${e.clientY}px`;
            contextMenu.style.left = `${e.clientX}px`;
            contextMenu.style.display = 'block';
        });
        
        // Закрываем меню при клике вне его
        document.addEventListener('click', (e) => {
            if (!e.target.closest('#messageContextMenu')) {
                const contextMenu = document.getElementById('messageContextMenu');
                if (contextMenu) contextMenu.style.display = 'none';
            }
        });
    },
    
    /**
     * Показывает информацию о сжатии сообщения
     * @param {string} messageId - ID сообщения
     */
    showMessageCompressionInfo: function(messageId) {
        // Отправляем запрос на получение информации о сжатии
        fetch(`/api/message_compression_info/${messageId}`)
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    // Создаем модальное окно, если его еще нет
                    let compressionModal = document.getElementById('compressionInfoModal');
                    
                    if (!compressionModal) {
                        compressionModal = document.createElement('div');
                        compressionModal.id = 'compressionInfoModal';
                        compressionModal.className = 'modal';
                        compressionModal.innerHTML = `
                            <div class="modal-content">
                                <div class="modal-header">
                                    <h3>Информация о сжатии</h3>
                                    <button class="close-modal">&times;</button>
                                </div>
                                <div class="modal-body compression-info">
                                    <div class="loading-indicator">
                                        <div class="spinner"></div>
                                        <p>Загрузка данных о сжатии...</p>
                                    </div>
                                </div>
                            </div>
                        `;
                        document.body.appendChild(compressionModal);
                        
                        // Добавляем обработчик закрытия
                        compressionModal.querySelector('.close-modal').addEventListener('click', () => {
                            compressionModal.style.display = 'none';
                        });
                        
                        // Закрываем при клике на фон
                        compressionModal.addEventListener('click', (e) => {
                            if (e.target === compressionModal) {
                                compressionModal.style.display = 'none';
                            }
                        });
                    }
                    
                    // Показываем модальное окно
                    compressionModal.style.display = 'block';
                    
                    // Форматируем размеры для лучшего отображения
                    const originalSizeFormatted = this.formatBytes(data.original_size);
                    const compressedSizeFormatted = this.formatBytes(data.compressed_size);
                    
                    // Формируем цвет для эффективности сжатия
                    let efficiencyColor = '#dc3545';  // красный для плохого сжатия
                    if (data.compression_ratio >= 50) {
                        efficiencyColor = '#28a745';  // зеленый для хорошего сжатия
                    } else if (data.compression_ratio >= 25) {
                        efficiencyColor = '#ffc107';  // желтый для среднего сжатия
                    }
                    
                    // Устанавливаем содержимое модального окна
                    compressionModal.querySelector('.modal-body').innerHTML = `
                        <div class="compression-stats">
                            <div class="stat-item">
                                <h4>Исходный размер</h4>
                                <p>${originalSizeFormatted}</p>
                            </div>
                            <div class="stat-item">
                                <h4>Сжатый размер</h4>
                                <p>${compressedSizeFormatted}</p>
                            </div>
                            <div class="stat-item">
                                <h4>Эффективность сжатия</h4>
                                <p style="color: ${efficiencyColor}; font-weight: bold;">${data.compression_ratio}%</p>
                            </div>
                        </div>
                        <div class="compression-details">
                            <h4>Метод сжатия</h4>
                            <p>${data.compression_method}</p>
                            <h4>Текст сообщения</h4>
                            <p class="message-preview">${data.text}</p>
                            <h4>Информация о сообщении</h4>
                            <p>ID: ${data.message_id}</p>
                            <p>Отправитель: ${data.sender}</p>
                            <p>Время: ${this.formatDateTime(new Date(data.timestamp * 1000))}</p>
                        </div>
                    `;
                    
                    // Добавляем стили, если их еще нет
                    if (!document.getElementById('compression-modal-styles')) {
                        const style = document.createElement('style');
                        style.id = 'compression-modal-styles';
                        style.textContent = `
                            .compression-stats {
                                display: grid;
                                grid-template-columns: repeat(3, 1fr);
                                gap: 16px;
                                margin-bottom: 24px;
                                text-align: center;
                            }
                            .stat-item {
                                padding: 16px;
                                border-radius: 8px;
                                background-color: var(--hover-bg);
                            }
                            .stat-item h4 {
                                margin-top: 0;
                                margin-bottom: 8px;
                                font-size: 14px;
                                color: var(--text-secondary);
                            }
                            .stat-item p {
                                margin: 0;
                                font-size: 18px;
                                font-weight: 600;
                            }
                            .compression-details h4 {
                                margin-top: 16px;
                                margin-bottom: 8px;
                                font-size: 16px;
                            }
                            .compression-details p {
                                margin: 8px 0;
                            }
                            .message-preview {
                                padding: 12px;
                                background-color: var(--hover-bg);
                                border-radius: 8px;
                                max-height: 100px;
                                overflow-y: auto;
                            }
                        `;
                        document.head.appendChild(style);
                    }
                } else {
                    // Показываем ошибку
                    this.showError(`Ошибка получения информации о сжатии: ${data.error}`);
                }
            })
            .catch(error => {
                console.error('Ошибка при получении информации о сжатии:', error);
                this.showError('Не удалось получить информацию о сжатии сообщения');
            });
    },
    
    /**
     * Форматирует размер в байтах в человекочитаемый формат
     * @param {number} bytes - Размер в байтах
     * @return {string} Форматированный размер с единицей измерения
     */
    formatBytes: function(bytes) {
        if (bytes === 0) return '0 Байт';
        
        const k = 1024;
        const sizes = ['Байт', 'КБ', 'МБ', 'ГБ'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    },
    
    /**
     * Форматирует дату и время
     * @param {Date} date - Объект даты
     * @return {string} Форматированная дата и время
     */
    formatDateTime: function(date) {
        return date.toLocaleString([], {
            year: 'numeric',
            month: 'numeric',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        });
    },

    /**
     * Копирует текст сообщения в буфер обмена
     * @param {string} messageId - ID сообщения
     */
    copyMessageText: function(messageId) {
        const messageEl = document.querySelector(`.message[data-message-id="${messageId}"]`);
        if (!messageEl) return;
        
        const textEl = messageEl.querySelector('.message-text');
        if (!textEl) return;
        
        const text = textEl.textContent;
        navigator.clipboard.writeText(text)
            .then(() => {
                this.showToast('Текст скопирован в буфер обмена');
            })
            .catch(err => {
                console.error('Ошибка при копировании текста:', err);
                this.showError('Не удалось скопировать текст');
            });
    },
    
    /**
     * Подготавливает ответ на сообщение
     * @param {string} messageId - ID сообщения
     */
    replyToMessage: function(messageId) {
        // Заглушка для будущей реализации
        this.showToast('Функция ответа на сообщение находится в разработке');
    },
    
    /**
     * Подготавливает пересылку сообщения
     * @param {string} messageId - ID сообщения
     */
    forwardMessage: function(messageId) {
        // Заглушка для будущей реализации
        this.showToast('Функция пересылки сообщения находится в разработке');
    },
    
    /**
     * Удаляет сообщение
     * @param {string} messageId - ID сообщения
     */
    deleteMessage: function(messageId) {
        // Реализация удаления сообщения через API
        fetch('/api/delete_message', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                message_id: messageId,
                delete_for: 'self'
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // Удаляем сообщение из DOM
                const messageEl = document.querySelector(`.message[data-message-id="${messageId}"]`);
                if (messageEl) {
                    messageEl.remove();
                    this.showToast('Сообщение удалено');
                }
            } else {
                this.showError(`Ошибка при удалении сообщения: ${data.error}`);
            }
        })
        .catch(error => {
            console.error('Ошибка при удалении сообщения:', error);
            this.showError('Не удалось удалить сообщение');
        });
    }
};

// Инициализация приложения при загрузке страницы
document.addEventListener('DOMContentLoaded', function() {
    Chat.init();
}); 