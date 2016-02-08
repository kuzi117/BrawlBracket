// Participant socket connection
var pSocket;

// Chat socket connection
var chatSocket;

// JSON data for lobby
var lobbyData;

// JSON data for player settings
var playerSettings;

// Lobby timer interval so it can be cleared/checked later
var lobbyTimer;

// Current page in the app
var currentPage;

// Challonge short name for the tourney
var tourneyName;

// Challonge participant id of current user
var participantId;


//////////////////
// SOCKET STUFF //
//////////////////

/**
 * Connect to the server. Called when the app is first loaded.
 * @param {string} newTourneyName - The short tourney name (Challonge URL suffix).
 * @param {string} newParticipantId - The participant's Challonge id.
 */
function brawlBracketInit(newTourneyName, newParticipantId) {
    tourneyName = newTourneyName;
    participantId = newParticipantId;
    
    pSocket = io.connect(window.location.origin + '/participant');
    chatSocket = io.connect(window.location.origin + '/chat');

    pSocket.on('error', function() {
        $('.content-wrapper').load(getContentURL('lobby-error'));
    });
    
    pSocket.on('connect', function() {
        console.log('connected');
    });
    
    pSocket.on('join lobby', function(data) {
        lobbyData = data.lobbyData;
        playerSettings = data.playerSettings;
        
        // Set empty previous state
        lobbyData.prevState = {
            'name': null
        };
        
        // Get menu option/page from URL hash
        hashPage = window.location.hash.substring(1);
        
        if ($('.bb-menu-option[page="' + hashPage + '"]').length > 0) {
            showPage(hashPage);
        }
        else {
            showPage('lobby');
        }
    
        // Add functionality to menu options
        $('.bb-menu-option').on('click', function(event) {
            showPage($(this).attr('page'));
            
            return false;
        });
    });
    
    pSocket.on('update lobby', function(data) {
        if (data.property == 'state') {
            lobbyData.prevState = lobbyData.state;
        }
        
        lobbyData[data.property] = data.value;
    });
    
    chatSocket.on('receive', function(data) {
        onReceiveChat($('.direct-chat[chatId=' + data.chatId + ']'), data.messageData, false);
    });
    
    chatSocket.on('receive log', function(data) {
        var chatBox = $('.direct-chat[chatId=' + data.chatId + ']');
        var msgBox = chatBox.find('.direct-chat-messages');
        
        msgBox.empty();
        
        for (id in data.log) {
            var msgData = data.log[id];
            onReceiveChat(chatBox, msgData, true);
        }
        
        // Skip to bottom
        msgBox.scrollTop(msgBox[0].scrollHeight);
    });
}


//////////////////////
// HELPER FUNCTIONS //
//////////////////////

/**
 * Get a content page's URL including tourney and participant data.
 * @param {string} pageName - The name of the page to load. Should exist at
 *   /app-content/<pageName>/<tourneyName>
 */
function getContentURL(pageName) {
    return '/app-content/' + pageName + '/' + tourneyName;
}

/**
 * Create a participant status DOM element.
 * @param {boolean} ready - If true, the status is "Ready," else "Not Ready."
 */
function createStatus(ready) {
    color = ready ? 'green' : 'yellow';
    status = ready ? 'Ready' : 'Not Ready';
    
    return $('<h2 class="description-status text-' + color + '">' + status + '</h2>');
}

/**
 * Create a chat message DOM element.
 * @param {string} name - The name of the sender.
 * @param {string} time - Date string representing the time the message was sent.
 * @param {string} avatar - The sender's avatar.
 * @param {string} text - The text of the message.
 * @param {boolean} right - Should be true for the current user's messages and false for others.
 */
function createChatMessage(name, time, avatar, text, right) {
    var messageRoot = $('<div class="direct-chat-msg"></div>');
    
    if (right) messageRoot.addClass('right');
    
    var info = $('<div class="direct-chat-info clearfix"></div>');
    
    var timeDate = new Date(time);
    var formattedTime = timeDate.toLocaleTimeString();
    var msgTime = $('<span class="direct-chat-timestamp"></span>').text(formattedTime);
    
    var msgName = $('<span class="direct-chat-name"></span>').text(name);
    
    // Align name with avatar and put timestamp on the other side
    if (right) {
        msgName.addClass('pull-right');
        msgTime.addClass('pull-left');
    }
    else {
        msgName.addClass('pull-left');
        msgTime.addClass('pull-right');
    }
    
    info.append(msgName);
    info.append(msgTime);
    messageRoot.append(info);
    
    messageRoot.append($('<img class="direct-chat-img">').attr('src', avatar));
    messageRoot.append($('<div class="direct-chat-text"></div>').text(text));
    
    return messageRoot;
}

/**
 * Left-pad a string with a given character.
 * @param {string} str - The string.
 * @param {number} count - The number of characters to pad to.
 * @param {string} padChar - The character to use for padding.
 */
function padString(str, count, padChar) {
    var pad = Array(count + 1).join(padChar);
    return pad.substring(0, pad.length - str.length) + str;
}

//////////////////
// UI FUNCTIONS //
//////////////////

/**
 * Show an app page, update the menu, and update the URL hash.
 * @param {string} pageName - The name of the page (see getContentURL()).
 */
function showPage(pageName) {
    if (!pSocket.connected) return;
    
    $('.bb-menu-option').removeClass('active');
    $('.bb-menu-option[page="' + pageName + '"]').addClass('active');
    
    var wrapper = $('.content-wrapper');
    wrapper.find('.content').trigger('destroy');
    wrapper.addClass('not-ready');
    wrapper.load(getContentURL(pageName), function() {
        wrapper.removeClass('not-ready');
    });
        
    if (window.history.replaceState) {
        window.history.replaceState(null, null, '#' + pageName);
    }
    else {
        window.location.hash = pageName;
    }
    currentPage = pageName;
}

/**
 * Add a callout at the top of the app. If a callout with this id exists, replace it.
 * @param {string} id - Unique identifier for this callout (suffix to "bb-callout-").
 * @param {string} type - One of {danger, info, warning, success}.
 * @param {string} title - Callout title (optional).
 * @param {string} message - Callout message (optional).
 * @param {string} animation - 'in'/'inOut'/'none'. Optional.
 * @returns {jQuery object} The callout object.
 */
function addCallout(id, type, title, message, animation) {
    removeCallout(id);
    
    var callout = $('<div class="callout callout-' + type + '" id="' + id + '"></div>');
    if (title) callout.append('<h4>' + title + '</h4>');
    if (message) callout.append('<p>' + message + '</p>');
    
    $('.callout-container').prepend(callout);
    
    if (animation) {
        switch (animation) {
            case 'in':
                callout.hide().slideDown();
                break;
                
            case 'inOut':
                callout.hide().slideDown().delay(3000).slideUp();
                break;
                
            case 'none':
            default:
                break;
        }
    }
    
    return callout;
}

/**
 * Remove a callout from the top of the app.
 * @param {string} id - Unique identifier for this callout (suffix to "bb-callout-").
 */
function removeCallout(id) {
    $('#bb-callout-' + id).remove();
}

/**
 * Receive a chat message.
 * @param {jQuery object} chatBox - The outermost element of the chat box.
 * @param {json} msgData - Message JSON data.
 *     @param {string} msgData.name - The name of the sender.
 *     @param {string} msgData.sentTime - Date string representing the time the message was sent.
 *     @param {string} msgData.avatar - The sender's avatar.
 *     @param {string} msgData.message - The text of the message.
 *     @param {string} msgData.senderId - The Challonge participant id of the sender.
 * @param {string} msgData - The string.
 */
function onReceiveChat(chatBox, msgData, instant) {
    var msg = createChatMessage(msgData.name, msgData.sentTime, msgData.avatar,
                                msgData.message, msgData.senderId == participantId);
    var msgBox = chatBox.find('.direct-chat-messages');
    
    // Only scroll down if user is already at bottom
    var atBottom = msgBox.scrollTop() + msgBox.innerHeight() >= msgBox[0].scrollHeight;
    
    msg.appendTo(msgBox);
    
    // Do this after append so we can get the actual height
    if (atBottom && !instant) {
        msgBox.animate({ scrollTop: msgBox[0].scrollHeight }, "slow");
    }
}

/**
 * Send a message from a chat box and empty the chat box.
 * Does nothing if the box is empty.
 * @param {jQuery object} chatBox - The outermost element of the chat box.
 */
function sendChat(chatBox) {
    var input = chatBox.find('.direct-chat-input');
    
    var message = input.val();
    if (message == '') return;
    
    chatSocket.emit('send', {
        'chatId': chatBox.attr('chatId'),
        'message': message
    });
    
    input.val('');
}

$.fn.extend({
    toggleDisabled: function() {
        return $(this).each(function() {
            if ($(this).hasClass('disabled')) {
                $(this).removeClass('disabled');
            }
            else {
                $(this).addClass('disabled');
            }
        });
    },
    
    setUpChatBox: function(chatId) {
        return $(this).each(function() {
            var chatBox = $(this);
            
            // Set chat id so we know which chat this links to
            chatBox.attr('chatId', chatId);
            
            // Make send button send
            chatBox.find('.direct-chat-send').on('click', function(event) {
                sendChat(chatBox);
                
                return false;
            });
            
            // Make enter button send
            chatBox.find('.direct-chat-input').keypress(function(e) {
                if (e.which == 13) {
                    sendChat(chatBox);
                }
            });
            
            // Request chat history to populate box
            chatSocket.emit('request log', {
                'chatId': chatId
            });
        });
    }
});