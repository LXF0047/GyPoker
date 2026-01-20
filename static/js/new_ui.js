// ========================================
// PyPoker New UI - 完整游戏逻辑
// ========================================

const PyPoker = {
    socket: null,
    wantsToStartFinalHands: false,
    wantsToResetScores: false,
    roomId: null,
    players: {},
    playerIds: [],
    ownerId: null,
    countdownInterval: null, // 倒计时定时器
    interactionCooldowns: {}, // 互动按钮冷却

    // ========================================
    // 图像配置 - 修改这些变量来自定义牌桌和扑克牌样式
    // ========================================
    config: {
        // 是否使用图像扑克牌（设置为 true 后需配置 cardImagePath）
        // **视觉优化**: 默认启用图片扑克牌以获得更佳视觉效果。
        // 请确保在 '/static/images/cards/' 目录下存放了 'spades_A.png', 'hearts_K.png' 等格式的图片文件。
        useCardImages: true,
        // 扑克牌图像路径模板，{suit} 和 {rank} 会被替换为实际值
        // 例如: '/static/images/cards/{suit}_{rank}.png'
        // suit: spades, clubs, diamonds, hearts
        // rank: 2-10, J, Q, K, A
        cardImagePath: '/static/images/cards/{suit}_{rank}.png',

        // 是否使用自定义牌背图像
        useCustomCardBack: true,
        // 牌背图像路径
        cardBackImage: '/static/images/card-back.png'
    },

    // 牌型名称
    scoreCategories: {
        0: "高牌",
        1: "一对",
        2: "两对",
        3: "三条",
        4: "顺子",
        5: "同花",
        6: "葫芦",
        7: "四条",
        8: "同花顺"
    },

    // 花色符号和颜色
    suitSymbols: { 0: '♠', 1: '♣', 2: '♦', 3: '♥' },
    suitColors: { 0: 'black', 1: 'black', 2: 'red', 3: 'red' },

    // 下注状态
    Player: {
        betMode: false,
        currentBet: 0,
        minBet: 0,
        maxBet: 0,

        updateBetDisplay: function() {
            const betInput = document.getElementById('bet-input');
            const betBtn = document.getElementById('bet-cmd');
            betInput.value = PyPoker.Player.currentBet;

            document.getElementById('decrease-bet').disabled = PyPoker.Player.currentBet <= PyPoker.Player.minBet;
            document.getElementById('decrease-bet-quick').disabled = PyPoker.Player.currentBet <= PyPoker.Player.minBet;
            document.getElementById('increase-bet').disabled = PyPoker.Player.currentBet >= PyPoker.Player.maxBet;
            document.getElementById('increase-bet-quick').disabled = PyPoker.Player.currentBet >= PyPoker.Player.maxBet;

            // Remove state classes first, including the default 'btn-raise' from HTML
            betBtn.classList.remove('btn-raise', 'btn-call-state', 'btn-allin-state', 'btn-bet-state', 'btn-check');

            if (PyPoker.Player.currentBet === 0) {
                betBtn.textContent = '过牌';
                betBtn.classList.add('btn-check');
            } else if (PyPoker.Player.currentBet === PyPoker.Player.minBet && PyPoker.Player.minBet > 0) {
                betBtn.textContent = '跟注 $' + PyPoker.Player.currentBet;
                betBtn.classList.add('btn-call-state');
            } else if (PyPoker.Player.currentBet === PyPoker.Player.maxBet) {
                betBtn.textContent = 'All In';
                betBtn.classList.add('btn-allin-state');
            } else {
                betBtn.textContent = '下注 $' + PyPoker.Player.currentBet;
                betBtn.classList.add('btn-bet-state');
            }
        },

        enableBetMode: function(message) {
            PyPoker.Player.betMode = true;
            PyPoker.Player.minBet = parseInt(message.min_bet);
            PyPoker.Player.maxBet = parseInt(message.max_bet);
            PyPoker.Player.currentBet = PyPoker.Player.minBet;

            document.getElementById('allin-bet').dataset.value = PyPoker.Player.maxBet;

            // 设置弃牌/Pass按钮
            const foldBtn = document.getElementById('fold-cmd');
            if (message.min_score) {
                foldBtn.textContent = 'Pass';
                foldBtn.classList.remove('btn-fold');
                foldBtn.classList.add('btn-check');
            } else {
                foldBtn.textContent = '弃牌';
                foldBtn.classList.add('btn-fold');
                foldBtn.classList.remove('btn-check');
            }

            PyPoker.Player.updateBetDisplay();
            document.getElementById('bet-controls').style.display = 'flex';
        },

        disableBetMode: function() {
            PyPoker.Player.betMode = false;
            document.getElementById('bet-controls').style.display = 'none';
        },

        toggleReadyStatus: function() {
            const readyBtn = document.getElementById('ready-btn');
            const statusIndicator = document.getElementById('status-indicator');

            if (readyBtn.value === 'Ready') {
                readyBtn.value = 'Cancel';
                statusIndicator.classList.add('ready');
                readyBtn.classList.add('cancel-state');
            } else {
                readyBtn.value = 'Ready';
                statusIndicator.classList.remove('ready');
                readyBtn.classList.remove('cancel-state');
            }
        }
    },

    // 日志记录
    Logger: {
        log: function(text) {
            const p0 = document.querySelector('#game-status p[data-key="0"]');
            const p1 = document.querySelector('#game-status p[data-key="1"]');
            const p2 = document.querySelector('#game-status p[data-key="2"]');
            const p3 = document.querySelector('#game-status p[data-key="3"]');
            const p4 = document.querySelector('#game-status p[data-key="4"]');

            if (p4) p4.textContent = p3 ? p3.textContent : '';
            if (p3) p3.textContent = p2 ? p2.textContent : '';
            if (p2) p2.textContent = p1 ? p1.textContent : '';
            if (p1) p1.textContent = p0 ? p0.textContent : '';
            if (p0) p0.textContent = text;
        }
    },

    // 聊天功能
    Chat: {
        sendMessage: function(message) {
            if (message.trim() !== '') {
                PyPoker.socket.emit('game_message', {
                    'message_type': 'chat_message',
                    'message': message
                });
            }
        },

        addMessage: function(senderId, senderName, message) {
            const chatMessagesContainer = document.getElementById('chat-messages-container');
            const msgDiv = document.createElement('div');
            msgDiv.className = 'msg';

            const currentPlayerId = document.getElementById('current-player').getAttribute('data-player-id');
            if (senderId == currentPlayerId) {
                msgDiv.classList.add('my-message');
            }

            const now = new Date();
            const time = `${now.getHours().toString().padStart(2,'0')}:${now.getMinutes().toString().padStart(2,'0')}`;
            msgDiv.innerHTML = `
                <span class="name">${senderName}:</span>
                <span class="time">${time}</span>
                ${message}
            `;

            const spacer = chatMessagesContainer.querySelector('div[style="flex: 1;"]');
            if (spacer) {
                chatMessagesContainer.insertBefore(msgDiv, spacer);
            } else {
                chatMessagesContainer.appendChild(msgDiv);
            }
            chatMessagesContainer.scrollTop = chatMessagesContainer.scrollHeight;

            // 显示气泡
            PyPoker.Game.showInteractionBubble(senderId, message);
        }
    },

    // 游戏逻辑
    Game: {
        gameId: null,
        dealerId: null,

        getCurrentPlayerId: function() {
            return document.getElementById('current-player').getAttribute('data-player-id');
        },

        // 花色名称映射（用于图像路径）
        suitNames: { 0: 'spades', 1: 'clubs', 2: 'diamonds', 3: 'hearts' },

        // 创建卡牌HTML
        createCard: function(rank, suit, size = 'medium') {
            // 牌背（未知牌）
            if (rank === undefined || suit === undefined) {
                const customBackClass = PyPoker.config.useCustomCardBack ? 'custom-back' : '';
                const backStyle = PyPoker.config.useCustomCardBack
                    ? `style="background-image: url('${PyPoker.config.cardBackImage}');"`
                    : '';
                return `<div class="card face-down ${size} ${customBackClass}" ${backStyle}></div>`;
            }

            const suitSymbol = PyPoker.suitSymbols[suit];
            const colorClass = PyPoker.suitColors[suit];
            let displayRank = rank;
            if (rank === 14 || rank === 1) displayRank = 'A';
            else if (rank === 13) displayRank = 'K';
            else if (rank === 12) displayRank = 'Q';
            else if (rank === 11) displayRank = 'J';

            // 使用图像扑克牌
            if (PyPoker.config.useCardImages) {
                const suitName = PyPoker.Game.suitNames[suit];
                const imagePath = PyPoker.config.cardImagePath
                    .replace('{suit}', suitName)
                    .replace('{rank}', displayRank);
                // 如果没有CSS类支持，可以在这里添加 style="width: 40px; height: 56px;" 等
                return `<div class="card card-image ${size}" style="background-image: url('${imagePath}');"></div>`;
            }

            // 默认符号样式
            return `
                <div class="card ${colorClass} ${size}">
                    <div class="card-corner top-left">
                        <span class="card-value">${displayRank}</span>
                        <span class="card-suit-small">${suitSymbol}</span>
                    </div>
                    <span class="card-suit-center">${suitSymbol}</span>
                    <div class="card-corner bottom-right">
                        <span class="card-value">${displayRank}</span>
                        <span class="card-suit-small">${suitSymbol}</span>
                    </div>
                </div>
            `;
        },

        // 新游戏开始
        newGame: function(message) {
            PyPoker.Game.gameId = message.game_id;
            PyPoker.Game.dealerId = message.dealer_id;

            // 隐藏玩家控制区
            document.getElementById('player-controls').style.display = 'none';

            // 清空游戏状态
            document.querySelectorAll('.seat').forEach(seat => {
                seat.classList.remove('fold', 'winner', 'active');
                const cards = seat.querySelector('.hand-cards');
                if (cards) cards.innerHTML = '';
                // 清除赢家金额提示
                const winAmount = seat.querySelector('.win-amount');
                if (winAmount) winAmount.remove();
            });
            // 清除所有下注
            document.querySelectorAll('.bet-area').forEach(el => el.remove());

            document.getElementById('community-cards').innerHTML = '';
            // 重置底池显示
            const potDisplay = document.querySelector('.pot-display');
            if (potDisplay) {
                potDisplay.innerHTML = '<div class="pot-label">Main Pot</div><div id="pot-amount" class="pot-amount">$0</div>';
            }
            document.querySelector('.pot-chips').innerHTML = '';
            
            document.getElementById('my-hand-display').innerHTML = ''; // 清空底部手牌显示

            // 停止并隐藏倒计时
            PyPoker.Game.stopCountdown();

            // 为每个玩家创建空白手牌
            for (let key in message.players) {
                const playerId = message.players[key].id;
                const seat = document.querySelector(`.seat[data-player-id="${playerId}"]`);
                if (seat) {
                    const cardsDiv = seat.querySelector('.hand-cards');
                    if (cardsDiv) {
                        // 修改此处: 传入 'small' 参数以调整座位上盖牌的大小
                        cardsDiv.innerHTML = PyPoker.Game.createCard(undefined, undefined, 'small') + PyPoker.Game.createCard(undefined, undefined, 'small');
                    }
                    // 标记庄家
                    if (playerId == message.dealer_id) {
                        let dealerBtn = seat.querySelector('.dealer-btn');
                        if (!dealerBtn) {
                            dealerBtn = document.createElement('div');
                            dealerBtn.className = 'dealer-btn';
                            dealerBtn.textContent = 'D';
                            seat.querySelector('.avatar-container').appendChild(dealerBtn);
                        }
                    } else {
                        const dealerBtn = seat.querySelector('.dealer-btn');
                        if (dealerBtn) dealerBtn.remove();
                    }
                }
            }

            PyPoker.Logger.log('新一局游戏开始');
        },

        // 更新玩家信息
        updatePlayer: function(player) {
            const seat = document.querySelector(`.seat[data-player-id="${player.id}"]`);
            if (seat) {
                const balance = seat.querySelector('.player-balance');
                if (balance) balance.textContent = '$' + parseInt(player.money);
                const name = seat.querySelector('.player-name');
                if (name && player.name) name.textContent = player.name;
            }
        },

        updatePlayers: function(players) {
            for (let k in players) {
                PyPoker.Game.updatePlayer(players[k]);
            }
        },

        // 下注位置坐标（基于原始桌面图 2816x1536 的像素坐标，左上角为 (0,0)）
        betPositionsPx: [
            { x: 2220, y: 1185 }, // Seat 0
            { x: 2445, y: 945  }, // Seat 1
            { x: 2430, y: 590  }, // Seat 2
            { x: 2160, y: 365  }, // Seat 3
            { x: 1675, y: 365  }, // Seat 4
            { x: 1140, y: 365  }, // Seat 5
            { x: 660,  y: 365  }, // Seat 6
            { x: 378,  y: 590  }, // Seat 7
            { x: 371,  y: 945  }, // Seat 8
            { x: 594,  y: 1185 }  // Seat 9
        ],

        // 原始桌面图尺寸（用于把像素坐标转换为百分比坐标）
        TABLE_ORIGINAL_SIZE: { width: 2816, height: 1536 },

        // 将像素坐标转换为百分比（用于绝对定位时随容器缩放自适应）
        // 注意：输入的 (x, y) 是以 **右下角为 (0,0)** 记录的像素坐标
        // 转换为以左上角为 (0,0) 后再换算百分比
        pxToPercentPos: function(x, y) {
            const w = PyPoker.Game.TABLE_ORIGINAL_SIZE.width;
            const h = PyPoker.Game.TABLE_ORIGINAL_SIZE.height;

            // 右下角原点 -> 左上角原点
            const xFromLeft = w - x;
            const yFromTop = h - y;

            return {
                left: (xFromLeft / w * 100).toFixed(2) + '%',
                top: (yFromTop / h * 100).toFixed(2) + '%'
            };
        },

        // 获取某个座位的下注位置（百分比）
        getBetPosition: function(seatIndex) {
            const p = PyPoker.Game.betPositionsPx[seatIndex];
            if (!p) return null;
            return PyPoker.Game.pxToPercentPos(p.x, p.y);
        },

        // 更新下注显示
        updatePlayersBet: function(bets) {
            // 移除所有现有下注显示
            document.querySelectorAll('.bet-area').forEach(el => el.remove());

            if (bets) {
                const seatsContainer = document.getElementById('seats-container');
                for (let playerId in bets) {
                    const bet = parseInt(bets[playerId]);
                    if (bet > 0) {
                        const seat = document.querySelector(`.seat[data-player-id="${playerId}"]`);
                        if (seat) {
                            const seatIndex = parseInt(seat.getAttribute('data-key'));
                            const pos = PyPoker.Game.getBetPosition(seatIndex);
                            
                            if (pos) {
                                const betArea = document.createElement('div');
                                betArea.className = 'bet-area';
                                betArea.style.position = 'absolute';
                                betArea.style.left = pos.left;
                                betArea.style.top = pos.top;
                                // 居中显示
                                betArea.style.transform = 'translate(-50%, -50%)';
                                
                                betArea.innerHTML = `
                                    <div class="bet-chips"><div class="chip chip-gold"></div></div>
                                    <div class="bet-amount">$${bet}</div>
                                `;
                                seatsContainer.appendChild(betArea);
                            }
                        }
                    }
                }
            }
        },

        // 玩家弃牌
        playerFold: function(player) {
            const seat = document.querySelector(`.seat[data-player-id="${player.id}"]`);
            if (seat) {
                seat.classList.add('fold');
            }
        },

        // 添加公共牌
        addSharedCards: function(cards) {
            const container = document.getElementById('community-cards');
            for (let i in cards) {
                container.innerHTML += PyPoker.Game.createCard(cards[i][0], cards[i][1]);
            }
        },

        // 更新底池
        updatePots: function(pots) {
            const potDisplay = document.querySelector('.pot-display');
            if (!potDisplay) return;
            
            potDisplay.innerHTML = '';
            let total = 0;
            
            if (!pots || pots.length === 0) {
                 potDisplay.innerHTML = '<div class="pot-label">Main Pot</div><div id="pot-amount" class="pot-amount">$0</div>';
            } else {
                // 计算总额
                for (let i in pots) {
                    total += parseInt(pots[i].money);
                }

                if (pots.length === 1) {
                    potDisplay.innerHTML = '<div class="pot-label">Main Pot</div><div id="pot-amount" class="pot-amount">$' + parseInt(pots[0].money) + '</div>';
                } else {
                    // 多边池显示
                    pots.forEach((pot, index) => {
                        const money = parseInt(pot.money);
                        const label = index === 0 ? 'Main Pot' : `Side Pot ${index}`;
                        
                        const row = document.createElement('div');
                        row.style.fontSize = '0.8em';
                        row.style.marginBottom = '2px';
                        row.innerHTML = `<span style="opacity:0.8">${label}:</span> <strong>$${money}</strong>`;
                        potDisplay.appendChild(row);
                    });
                }
            }

            const potChips = document.querySelector('.pot-chips');
            if (potChips) {
                if (total > 0) {
                    potChips.innerHTML = '<div class="chip chip-gold"></div>';
                } else {
                    potChips.innerHTML = '';
                }
            }
        },

        // 设置赢家
        setWinners: function(pot) {
            document.querySelectorAll('.seat').forEach(seat => {
                seat.classList.add('fold');
                seat.classList.remove('winner');
                // 移除旧的赢钱提示
                const oldWin = seat.querySelector('.win-amount');
                if (oldWin) oldWin.remove();
            });

            const moneySplit = pot.money_split;

            for (let i in pot.winner_ids) {
                const winnerId = pot.winner_ids[i];
                const seat = document.querySelector(`.seat[data-player-id="${winnerId}"]`);
                if (seat) {
                    seat.classList.remove('fold');
                    seat.classList.add('winner');
                    
                    // 显示赢得金额
                    const winLabel = document.createElement('div');
                    winLabel.className = 'win-amount';
                    winLabel.textContent = `+$${moneySplit}`;
                    // 简单的内联样式
                    winLabel.style.position = 'absolute';
                    winLabel.style.top = '-30px';
                    winLabel.style.width = '100%';
                    winLabel.style.textAlign = 'center';
                    winLabel.style.color = '#FFD700';
                    winLabel.style.fontWeight = 'bold';
                    winLabel.style.fontSize = '1.2em';
                    winLabel.style.textShadow = '0 2px 4px rgba(0,0,0,0.8)';
                    winLabel.style.zIndex = '100';
                    
                    // 确保 seat 是 relative 或 absolute 定位
                    if (getComputedStyle(seat).position === 'static') {
                        seat.style.position = 'relative';
                    }
                    
                    seat.appendChild(winLabel);
                }
            }
        },

        // 显示玩家手牌
        updatePlayersCards: function(players) {
            for (let playerId in players) {
                const seat = document.querySelector(`.seat[data-player-id="${playerId}"]`);
                if (seat && players[playerId].cards) {
                    const cardsDiv = seat.querySelector('.hand-cards');
                    if (cardsDiv) {
                        cardsDiv.innerHTML = '';
                        for (let i in players[playerId].cards) {
                            const card = players[playerId].cards[i];
                            // 修改此处: 传入 'small' 参数以调整摊牌时座位上手牌的大小
                            cardsDiv.innerHTML += PyPoker.Game.createCard(card[0], card[1], 'small');
                        }
                    }
                }
            }
        },

        // 更新当前玩家手牌
        updateCurrentPlayerCards: function(cards, score) {
            const currentPlayerId = PyPoker.Game.getCurrentPlayerId();
            const seat = document.querySelector(`.seat[data-player-id="${currentPlayerId}"]`);
            if (seat) {
                const cardsDiv = seat.querySelector('.hand-cards');
                if (cardsDiv) {
                    cardsDiv.innerHTML = '';
                    for (let i in cards) {
                        // 修改此处: 传入 'small' 参数以调整当前玩家座位上手牌的大小
                        cardsDiv.innerHTML += PyPoker.Game.createCard(cards[i][0], cards[i][1], 'small');
                    }
                }
            }
            
            // 同时更新底部操作栏左侧的手牌显示
            const myHandDisplay = document.getElementById('my-hand-display');
            if (myHandDisplay) {
                myHandDisplay.innerHTML = '';
                for (let i in cards) {
                    myHandDisplay.innerHTML += PyPoker.Game.createCard(cards[i][0], cards[i][1]);
                }
            }
        },
        
        // 游戏结束
        gameOver: function() {
            document.getElementById('ready-btn').value = 'Ready';
            document.getElementById('status-indicator').classList.remove('ready');
            document.getElementById('ready-btn').classList.remove('cancel-state'); // Reset cancel state
            // 显示玩家控制区
            document.getElementById('player-controls').style.display = 'flex';
            PyPoker.Player.disableBetMode();
            PyPoker.Game.fetchRankingData();
            PyPoker.Game.stopCountdown(); // 确保倒计时停止
            PyPoker.Logger.log('本局游戏结束');
        },

        // 处理游戏更新事件
        onGameUpdate: function(message) {
            PyPoker.Player.disableBetMode();

            switch (message.event) {
                case 'new-game':
                    PyPoker.Game.newGame(message);
                    break;
                case 'cards-assignment':
                    PyPoker.Game.updateCurrentPlayerCards(message.cards, message.score);
                    break;
                case 'game-over':
                    PyPoker.Game.gameOver();
                    break;
                case 'fold':
                    PyPoker.Game.playerFold(message.player);
                    break;
                case 'bet':
                    PyPoker.Game.updatePlayer(message.player);
                    PyPoker.Game.updatePlayersBet(message.bets);
                    break;
                case 'pots-update':
                    PyPoker.Game.updatePlayers(message.players);
                    PyPoker.Game.updatePots(message.pots);
                    PyPoker.Game.updatePlayersBet();
                    break;
                case 'player-action':
                    PyPoker.Game.onPlayerAction(message);
                    break;
                case 'dead-player':
                    PyPoker.Game.playerFold(message.player);
                    break;
                case 'shared-cards':
                    PyPoker.Game.addSharedCards(message.cards);
                    break;
                case 'winner-designation':
                    PyPoker.Game.updatePlayers(message.players);
                    PyPoker.Game.updatePots(message.pots);
                    PyPoker.Game.setWinners(message.pot);
                    break;
                case 'showdown':
                    PyPoker.Game.updatePlayersCards(message.players);
                    break;
                case 'update-ranking-data':
                    PyPoker.Game.updateRankingList(message.ranking_list);
                    break;
            }
        },

        // 启动倒计时
        startCountdown: function(seconds) {
            PyPoker.Game.stopCountdown(); // 清除旧的
            
            const countdownEl = document.getElementById('dealer-countdown');
            if (!countdownEl) return;
            
            let timeLeft = seconds;
            countdownEl.textContent = timeLeft;
            countdownEl.style.display = 'flex';
            
            PyPoker.countdownInterval = setInterval(() => {
                timeLeft--;
                if (timeLeft <= 0) {
                    PyPoker.Game.stopCountdown();
                    // 倒计时结束，自动弃牌
                    if (PyPoker.Player.betMode) {
                        PyPoker.socket.emit('game_message', {
                            'message_type': 'bet',
                            'bet': -1
                        });
                        PyPoker.Player.disableBetMode();
                    }
                } else {
                    countdownEl.textContent = timeLeft;
                }
            }, 1000);
        },
        
        // 停止倒计时
        stopCountdown: function() {
            if (PyPoker.countdownInterval) {
                clearInterval(PyPoker.countdownInterval);
                PyPoker.countdownInterval = null;
            }
            const countdownEl = document.getElementById('dealer-countdown');
            if (countdownEl) {
                countdownEl.style.display = 'none';
            }
        },

        // 处理玩家行动请求
        onPlayerAction: function(message) {
            const currentPlayerId = PyPoker.Game.getCurrentPlayerId();
            const isCurrentPlayer = message.player.id == currentPlayerId;

            // 标记当前行动玩家
            document.querySelectorAll('.seat').forEach(seat => seat.classList.remove('active'));
            const activeSeat = document.querySelector(`.seat[data-player-id="${message.player.id}"]`);
            if (activeSeat) activeSeat.classList.add('active');

            // 启动倒计时
            // 使用服务器传来的 timeout 值，如果没有则默认 15 秒
            const timeout = message.timeout || 15;
            PyPoker.Game.startCountdown(timeout);

            if (isCurrentPlayer && message.action === 'bet') {
                PyPoker.Player.enableBetMode(message);
            }
        },

        // 更新排行榜
        updateRankingList: function(data) {
            const rankPanel = document.getElementById('panel-rank');
            rankPanel.innerHTML = `
                <table class="ranking-table">
                    <thead>
                        <tr>
                            <th>#</th>
                            <th>玩家</th>
                            <th>总积分</th>
                            <th>bb/100</th>
                            <th>当日</th>
                            <th>净胜</th>
                        </tr>
                    </thead>
                    <tbody></tbody>
                </table>
            `;
            
            const tbody = rankPanel.querySelector('tbody');
            const rankEmojis = ['🥇', '🥈', '🥉'];

            data.forEach((player, index) => {
                const [rank, playerName, totalScore, bbPer100, dailyTotal, dailyProfit] = player;
                const row = document.createElement('tr');
                
                // Format profit with sign and color
                const profitClass = dailyProfit > 0 ? 'profit-pos' : (dailyProfit < 0 ? 'profit-neg' : 'profit-neutral');
                const profitSign = dailyProfit > 0 ? '+' : '';
                
                row.innerHTML = `
                    <td class="col-rank">${rankEmojis[index] || rank}</td>
                    <td class="col-name">${playerName}</td>
                    <td class="col-total">${totalScore}</td>
                    <td class="col-bb">${bbPer100}</td>
                    <td class="col-daily">${dailyTotal}</td>
                    <td class="col-profit ${profitClass}">${profitSign}${dailyProfit}</td>
                `;
                tbody.appendChild(row);
            });
        },

        fetchRankingData: function() {
            fetch('/api/get-ranking')
                .then(response => response.json())
                .then(data => {
                    if (data && Array.isArray(data)) {
                        PyPoker.Game.updateRankingList(data);
                    }
                })
                .catch(error => console.error('Failed to fetch ranking:', error));
        },

        // 显示互动气泡
        showInteractionBubble: function(senderId, text) {
            const seat = document.querySelector(`.seat[data-player-id="${senderId}"]`);
            if (!seat) return;

            const avatarContainer = seat.querySelector('.avatar-container');
            if (!avatarContainer) return;

            // 移除旧的气泡
            const oldBubble = avatarContainer.querySelector('.interaction-bubble');
            if (oldBubble) oldBubble.remove();

            const bubble = document.createElement('div');
            bubble.className = 'interaction-bubble';
            bubble.textContent = text;
            avatarContainer.appendChild(bubble);

            // 3秒后移除
            setTimeout(() => {
                bubble.remove();
            }, 3000);
        },

        // 播放音效
        playSound: function(action) {
            const audio = new Audio(`/static/sounds/${action}.mp3`);
            audio.play().catch(e => console.log('Audio play failed:', e));
        }
    },

    // 房间管理
    Room: {
        initRoom: function(message) {
            console.log("initRoom called with message:", message);
            PyPoker.roomId = message.room_id;
            PyPoker.players = message.players;
            PyPoker.playerIds = message.player_ids;
            PyPoker.ownerId = message.owner_id;

            const seatsContainer = document.getElementById('seats-container');
            seatsContainer.innerHTML = '';

            // 限制最多显示10个座位
            const maxSeats = 10;
            const seatCount = Math.min(message.player_ids.length, maxSeats);
            for (let k = 0; k < seatCount; k++) {
                const playerId = message.player_ids[k];
                const seatDiv = document.createElement('div');
                seatDiv.className = `seat seat-${k}`;
                seatDiv.setAttribute('data-key', k);

                if (playerId && message.players[playerId]) {
                    const player = message.players[playerId];
                    const isCurrentPlayer = playerId == PyPoker.Game.getCurrentPlayerId();
                    seatDiv.setAttribute('data-player-id', playerId);
                    if (isCurrentPlayer) seatDiv.classList.add('current-player-seat');

                    seatDiv.innerHTML = `
                        <div class="avatar-container">
                            <div class="avatar">${player.name.charAt(0).toUpperCase()}</div>
                        </div>
                        <div class="player-info">
                            <div class="player-name">${isCurrentPlayer ? 'You' : player.name}</div>
                            <div class="player-balance">$${parseInt(player.money)}</div>
                        </div>
                        <div class="hand-cards"></div>
                    `;
                } else {
                    seatDiv.classList.add('empty');
                    seatDiv.innerHTML = `
                        <div class="avatar-container">
                            <div class="avatar"></div>
                        </div>
                    `;
                }
                seatsContainer.appendChild(seatDiv);
            }
        },

        onRoomUpdate: function(message) {
            console.log("onRoomUpdate:", message);
            if (PyPoker.roomId === null) {
                PyPoker.Room.initRoom(message);
            }

            PyPoker.ownerId = message.owner_id;
            const currentPlayerId = PyPoker.Game.getCurrentPlayerId();

            // 房主功能按钮显示
            if (message.owner_id == currentPlayerId) {
                document.getElementById('last-10-hands-btn').style.display = 'inline-block';
                document.getElementById('reset-scores-btn').style.display = 'inline-block';
            } else {
                document.getElementById('last-10-hands-btn').style.display = 'none';
                document.getElementById('reset-scores-btn').style.display = 'none';
            }

            // 更新房主名称
            if (message.owner_id && message.players[message.owner_id]) {
                document.getElementById('room-owner-name').textContent = message.players[message.owner_id].name;
            }

            switch (message.event) {
                case 'player-added':
                case 'player-rejoined':
                    const pId = message.player_id;
                    const pData = message.players[pId];
                    const pName = pId == currentPlayerId ? 'You' : pData.name;
                    
                    if (message.event === 'player-added') {
                        PyPoker.Logger.log(pName + ' 加入了房间');
                    } else {
                        PyPoker.Logger.log(pName + ' 重新连接');
                    }

                    // Update local state
                    PyPoker.players = message.players;
                    PyPoker.playerIds = message.player_ids;

                    document.querySelectorAll('.seat').forEach(seat => {
                        const key = parseInt(seat.getAttribute('data-key'));
                        const playerId = message.player_ids[key];
                        
                        if (playerId && message.players[playerId]) {
                            const player = message.players[playerId];
                            const isCurrentPlayer = playerId == currentPlayerId;
                            
                            // Update if seat is empty or has different player
                            if (seat.classList.contains('empty') || seat.getAttribute('data-player-id') != playerId) {
                                seat.classList.remove('empty');
                                seat.setAttribute('data-player-id', playerId);
                                if (isCurrentPlayer) seat.classList.add('current-player-seat');
                                else seat.classList.remove('current-player-seat');
                                
                                seat.innerHTML = `
                                    <div class="avatar-container">
                                        <div class="avatar">${player.name.charAt(0).toUpperCase()}</div>
                                    </div>
                                    <div class="player-info">
                                        <div class="player-name">${isCurrentPlayer ? 'You' : player.name}</div>
                                        <div class="player-balance">$${parseInt(player.money)}</div>
                                    </div>
                                    <div class="hand-cards"></div>
                                `;
                            } else {
                                // Seat already occupied by this player, just update info
                                const balance = seat.querySelector('.player-balance');
                                if (balance) balance.textContent = '$' + parseInt(player.money);
                                const name = seat.querySelector('.player-name');
                                if (name) name.textContent = isCurrentPlayer ? 'You' : player.name;
                            }
                        } else {
                            // Seat should be empty
                            if (!seat.classList.contains('empty')) {
                                seat.classList.add('empty');
                                seat.classList.remove('current-player-seat');
                                seat.removeAttribute('data-player-id');
                                seat.innerHTML = `
                                    <div class="avatar-container">
                                        <div class="avatar"></div>
                                    </div>
                                `;
                            }
                        }
                    });
                    break;

                case 'player-removed':
                    // Update local state
                    PyPoker.players = message.players;
                    PyPoker.playerIds = message.player_ids;

                    const removedSeat = document.querySelector(`.seat[data-player-id="${message.player_id}"]`);
                    if (removedSeat) {
                        const playerName = removedSeat.querySelector('.player-name')?.textContent || 'Player';
                        PyPoker.Logger.log(playerName + ' 离开了房间');
                        removedSeat.classList.add('empty');
                        removedSeat.classList.remove('current-player-seat');
                        removedSeat.removeAttribute('data-player-id');
                        removedSeat.innerHTML = `
                            <div class="avatar-container">
                                <div class="avatar"></div>
                            </div>
                        `;
                    }
                    break;
            }
        }
    },

    // 初始化
    init: function() {
        PyPoker.socket = io();

        PyPoker.socket.on('connect', function() {
            PyPoker.Logger.log('已连接到服务器');
            PyPoker.socket.emit('join_game', {});
        });

        PyPoker.socket.on('disconnect', function() {
            PyPoker.Logger.log('与服务器断开连接');
            PyPoker.roomId = null;
            document.getElementById('seats-container').innerHTML = '';
        });

        PyPoker.socket.on('game_connected', function(data) {
            PyPoker.Logger.log('成功连接到游戏服务器');
            
            let playerId = data.player_id;
            if (!playerId && data.player && data.player.id) {
                playerId = data.player.id;
            }
            
            if (playerId) {
                document.getElementById('current-player').setAttribute('data-player-id', playerId);
            }

            if (data.message_type === 'room-update') {
                PyPoker.Room.onRoomUpdate(data);
            }
        });

        PyPoker.socket.on('game_message', function(data) {
            switch (data.message_type) {
                case 'ping':
                    const readyBtn = document.getElementById('ready-btn');
                    const isReady = readyBtn.value === 'Cancel';
                    let pongMsg = {
                        'message_type': 'pong',
                        'ready': isReady
                    };
                    if (PyPoker.wantsToStartFinalHands) {
                        pongMsg.start_final_10_hands = true;
                        PyPoker.wantsToStartFinalHands = false;
                    }
                    if (PyPoker.wantsToResetScores) {
                        pongMsg.reset_scores = true;
                        PyPoker.wantsToResetScores = false;
                    }
                    PyPoker.socket.emit('game_message', pongMsg);
                    break;

                case 'room-update':
                    PyPoker.Room.onRoomUpdate(data);
                    break;

                case 'game-update':
                    PyPoker.Game.onGameUpdate(data);
                    break;

                case 'chat_message':
                    PyPoker.Chat.addMessage(data.sender_id, data.sender_name, data.message);
                    break;
                
                case 'interaction':
                    const actionMap = {
                        'yanpai': '我要验牌',
                        'meiwenti': '牌没有问题',
                        'kaipai': '来，开牌'
                    };
                    if (actionMap[data.action]) {
                        PyPoker.Game.showInteractionBubble(data.sender_id, actionMap[data.action]);
                        PyPoker.Game.playSound(data.action);
                    }
                    break;

                case 'final-hands-started':
                    document.getElementById('last-10-hands-btn').style.display = 'none';
                    document.getElementById('hand-countdown-display').textContent = `最后 ${data.countdown} 把开始`;
                    document.getElementById('hand-countdown-display').style.display = 'inline-block';
                    PyPoker.Logger.log('最后 ' + data.countdown + ' 把游戏开始');
                    break;

                case 'final-hands-update':
                    document.getElementById('hand-countdown-display').textContent = `第 ${data.current_hand} / ${data.total_hands} 局`;
                    break;

                case 'final-hands-finished':
                    alert('10局游戏已结束。');
                    document.getElementById('hand-countdown-display').style.display = 'none';
                    document.getElementById('last-10-hands-btn').value = '最后10把';
                    document.getElementById('last-10-hands-btn').disabled = false;
                    document.getElementById('last-10-hands-btn').style.display = 'inline-block';
                    break;
            }
        });

        PyPoker.socket.on('error', function(data) {
            PyPoker.Logger.log('错误: ' + data.error);
        });

        // 获取初始排行榜
        PyPoker.Game.fetchRankingData();

        // === 事件绑定 ===

        // Ready 按钮
        document.getElementById('ready-btn').addEventListener('click', function() {
            PyPoker.Player.toggleReadyStatus();
        });

        // 最后10把按钮
        document.getElementById('last-10-hands-btn').addEventListener('click', function() {
            PyPoker.wantsToStartFinalHands = true;
            this.value = '下把开始最后10把';
            this.disabled = true;
        });

        // 清空积分按钮
        document.getElementById('reset-scores-btn').addEventListener('click', function() {
            if (confirm('确定要清空所有玩家的积分吗？此操作不可逆转。')) {
                PyPoker.wantsToResetScores = true;
                this.value = '请求已发送';
                this.disabled = true;
            }
        });

        // 弃牌按钮
        document.getElementById('fold-cmd').addEventListener('click', function() {
            PyPoker.socket.emit('game_message', {
                'message_type': 'bet',
                'bet': -1
            });
            PyPoker.Player.disableBetMode();
            PyPoker.Game.stopCountdown(); // 停止倒计时
        });

        // 下注按钮
        document.getElementById('bet-cmd').addEventListener('click', function() {
            PyPoker.socket.emit('game_message', {
                'message_type': 'bet',
                'bet': PyPoker.Player.currentBet
            });
            PyPoker.Player.disableBetMode();
            PyPoker.Game.stopCountdown(); // 停止倒计时
        });

        // 等待按钮
        document.getElementById('no-bet-cmd').addEventListener('click', function() {
            PyPoker.socket.emit('game_message', {
                'message_type': 'bet',
                'bet': 0
            });
            PyPoker.Player.disableBetMode();
            PyPoker.Game.stopCountdown(); // 停止倒计时
        });

        // 减少下注
        document.getElementById('decrease-bet').addEventListener('click', function() {
            if (PyPoker.Player.currentBet > PyPoker.Player.minBet) {
                PyPoker.Player.currentBet = Math.max(PyPoker.Player.minBet, PyPoker.Player.currentBet - 10);
                PyPoker.Player.updateBetDisplay();
            }
        });

        document.getElementById('decrease-bet-quick').addEventListener('click', function() {
            if (PyPoker.Player.currentBet > PyPoker.Player.minBet) {
                PyPoker.Player.currentBet = Math.max(PyPoker.Player.minBet, PyPoker.Player.currentBet - 50);
                PyPoker.Player.updateBetDisplay();
            }
        });

        // 增加下注
        document.getElementById('increase-bet').addEventListener('click', function() {
            if (PyPoker.Player.currentBet < PyPoker.Player.maxBet) {
                PyPoker.Player.currentBet = Math.min(PyPoker.Player.maxBet, PyPoker.Player.currentBet + 10);
                PyPoker.Player.updateBetDisplay();
            }
        });

        document.getElementById('increase-bet-quick').addEventListener('click', function() {
            if (PyPoker.Player.currentBet < PyPoker.Player.maxBet) {
                PyPoker.Player.currentBet = Math.min(PyPoker.Player.maxBet, PyPoker.Player.currentBet + 50);
                PyPoker.Player.updateBetDisplay();
            }
        });

        // 半池
        document.getElementById('half-pot-bet').addEventListener('click', function() {
            const potText = document.getElementById('pot-amount').textContent;
            const potAmount = parseInt(potText.replace('$', '').replace(',', '')) || 0;
            const halfPot = Math.round(potAmount / 2);
            PyPoker.Player.currentBet = Math.max(PyPoker.Player.minBet, Math.min(PyPoker.Player.maxBet, halfPot));
            PyPoker.Player.updateBetDisplay();
        });

        // 全池
        document.getElementById('full-pot-bet').addEventListener('click', function() {
            const potText = document.getElementById('pot-amount').textContent;
            const potAmount = parseInt(potText.replace('$', '').replace(',', '')) || 0;
            PyPoker.Player.currentBet = Math.max(PyPoker.Player.minBet, Math.min(PyPoker.Player.maxBet, potAmount));
            PyPoker.Player.updateBetDisplay();
        });

        // All-in
        document.getElementById('allin-bet').addEventListener('click', function() {
            if (confirm('您确定要全下 (All-In) 吗？')) {
                PyPoker.socket.emit('game_message', {
                    'message_type': 'bet',
                    'bet': PyPoker.Player.maxBet
                });
                PyPoker.Player.disableBetMode();
                PyPoker.Game.stopCountdown(); // 停止倒计时
            }
        });

        PyPoker.Player.disableBetMode();
    }
};

// 发送互动消息
function sendInteraction(action) {
    const now = Date.now();
    const lastTime = PyPoker.interactionCooldowns[action] || 0;
    const cooldown = 5000; // 5秒冷却

    if (now - lastTime < cooldown) {
        return;
    }

    PyPoker.interactionCooldowns[action] = now;
    
    // 更新按钮状态
    const btn = document.querySelector(`.interaction-btn[data-action="${action}"]`);
    if (btn) {
        btn.disabled = true;
        let timeLeft = 5;
        btn.textContent = timeLeft;
        
        const interval = setInterval(() => {
            timeLeft--;
            if (timeLeft <= 0) {
                clearInterval(interval);
                btn.disabled = false;
                const actionMap = {
                    'yanpai': '我要验牌',
                    'meiwenti': '牌没有问题',
                    'kaipai': '来，开牌'
                };
                btn.textContent = actionMap[action];
            } else {
                btn.textContent = timeLeft;
            }
        }, 1000);
    }

    PyPoker.socket.emit('game_message', {
        'message_type': 'interaction',
        'action': action
    });
}

// UI 辅助函数
function toggleSidebar() {
    document.getElementById('sidebar').classList.toggle('open');
    document.getElementById('sidebar-overlay').classList.toggle('active');
}

function switchTab(tab, event) {
    document.getElementById('panel-chat').style.display = tab === 'chat' ? 'flex' : 'none';
    document.getElementById('panel-rank').style.display = tab === 'rank' ? 'block' : 'none';
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    event.target.classList.add('active');

    if (tab === 'rank') {
        PyPoker.Game.fetchRankingData();
    }
}

function handleChat(e) {
    if (e.key === 'Enter' && e.target.value.trim() !== '') {
        PyPoker.Chat.sendMessage(e.target.value.trim());
        e.target.value = '';
    }
}

// 初始化
document.addEventListener('DOMContentLoaded', function() {
    PyPoker.init();
});
