PyPoker = {

    socket: null,

    Game: {
        gameId: null,

        numCards: null,

        scoreCategories: null,

        getCurrentPlayerId: function () {
            return $('#current-player').attr('data-player-id');
        },

        setCard: function ($card, rank, suit) {
            $card.each(function () {
                x = 0;
                y = 0;

                if ($(this).hasClass('small')) {
                    url = "static/images/cards-small.png";
                    width = 24;
                    height = 40;
                } else if ($(this).hasClass('medium')) {
                    url = "static/images/cards-medium.png";
                    width = 45;
                    height = 75;
                } else {
                    url = "static/images/cards-large.png";
                    width = 75;
                    height = 125;
                }

                if (rank !== undefined || suit !== undefined) {
                    switch (suit) {
                        case 0:
                            // Spades
                            x -= width;
                            y -= height;
                            break;
                        case 1:
                            // Clubs
                            y -= height;
                            break;
                        case 2:
                            // Diamonds
                            x -= width;
                            break;
                        case 3:
                            // Hearts
                            break;
                        default:
                            throw "Invalid suit";
                    }

                    if (rank == 14) {
                        rank = 1;
                    } else if (rank < 1 || rank > 13) {
                        throw "Invalid rank";
                    }

                    x -= (rank - 1) * 2 * width + width;
                }

                $(this).css('background-position', x + "px " + y + "px");
                $(this).css('background-image', 'url(' + url + ')');
            })
        },

        newGame: function (message) {
            PyPoker.Game.gameId = message.game_id;
            PyPoker.Game.emptyGameRecord();

            PyPoker.Game.numCards = 2;
            PyPoker.Game.scoreCategories = {
                0: "Highest card",
                1: "Pair",
                2: "Double pair",
                3: "Three of a kind",
                4: "Straight",
                5: "Flush",
                6: "Full house",
                7: "Four of a kind",
                8: "Straight flush"
            };


            $('#game-wrapper').addClass(message.game_type);

            for (key in message.players) {
                playerId = message.players[key].id
                $player = $('#players .player[data-player-id=' + playerId + ']');
                $cards = $('.cards', $player);
                for (i = 0; i < PyPoker.Game.numCards; i++) {
                    $cards.append('<div class="card small" data-key="' + i + '"></div>');
                }

                if (playerId == message.dealer_id) {
                    $player.addClass('dealer');
                }
                if (playerId == PyPoker.Game.getCurrentPlayerId()) {
                    $player.addClass('current');
                }
            }
            $('#current-player').show();
        },

        emptyGameRecord: function () {
            //游戏开始前清空上局游戏状态
            $('.player').removeClass('fold');
            $('.player').removeClass('winner');
            $('.player').removeClass('looser');
            $('.player').removeClass('dealer');
            $('.player .cards').empty();
            $('#pots').empty();
            $('#shared-cards').empty();
            $('#players .player .bet-wrapper').empty();
            $('#current-player').hide();
        },

        gameOver: function (message) {
            //ready-btn改为Ready，指示器改为红色
            $('#ready-btn').val('Ready');
            $('#status-indicator').css('background-color', 'red');
        },

        updatePlayer: function (player) {
            $player = $('#players .player[data-player-id=' + player.id + ']');
            $('.player-money', $player).text('$' + parseInt(player.money));
            $('.player-name', $player).text(player.name);
        },

        playerFold: function (player) {
            $('#players .player[data-player-id=' + player.id + ']').addClass('fold');
        },

        updatePlayers: function (players) {
            for (k in players) {
                PyPoker.Game.updatePlayer(players[k]);
            }
        },

        updatePlayersBet: function (bets) {
            // Remove bets
            $('#players .player .bet-wrapper').empty();
            if (bets !== undefined) {
                for (playerId in bets) {
                    bet = parseInt(bets[playerId]);
                    if (bet > 0) {
                        $bet = $('<div class="bet"></div>');
                        $bet.text('$' + parseInt(bets[playerId]));
                        $('#players .player[data-player-id=' + playerId + '] .bet-wrapper').append($bet);
                    }
                }
            }
        },

        setPlayerCards: function (cards, $cards) {
            for (cardKey in cards) {
                $card = $('.card[data-key=' + cardKey + ']', $cards);
                PyPoker.Game.setCard(
                    $card,
                    cards[cardKey][0],
                    cards[cardKey][1]
                );
            }
        },

        updatePlayersCards: function (players) {
            for (playerId in players) {
                $cards = $('.player[data-player-id=' + playerId + '] .cards');
                PyPoker.Game.setPlayerCards(players[playerId].cards, $cards);
            }
        },

        updateCurrentPlayerCards: function (cards, score) {
            $cards = $('.player[data-player-id=' + PyPoker.Game.getCurrentPlayerId() + '] .cards');
            PyPoker.Game.setPlayerCards(cards, $cards);
            $('#current-player .cards .category').text(PyPoker.Game.scoreCategories[score.category]);
        },

        addSharedCards: function (cards) {
            for (cardKey in cards) {
                $card = $('<div class="card medium"></div>');
                PyPoker.Game.setCard($card, cards[cardKey][0], cards[cardKey][1]);
                $('#shared-cards').append($card);
            }
        },

        updatePots: function (pots) {
            $('#pots').empty();
            for (potIndex in pots) {
                $('#pots').append($('<div class="pot">' + '$' + parseInt(pots[potIndex].money) + '</div>'));
            }
        },

        setWinners: function (pot) {
            $('#players .player').addClass('fold');
            $('#players .player').removeClass('winner');
            for (playerIdKey in pot.player_ids) {
                playerId = pot.player_ids[playerIdKey];

                $player = $('#players .player[data-player-id=' + playerId + ']');
                if (pot.winner_ids.indexOf(playerId) != -1) {
                    $player.removeClass('fold');
                    $player.addClass('winner');
                } else {
                    $player.addClass('fold');
                }
            }
        },

        changeCards: function (player, numCards) {
            $player = $('#players .player[data-player-id=' + player.id + ']');

            $cards = $('.card', $player).slice(-numCards);

            $cards.slideUp(1000).slideDown(1000);
        },

        onGameUpdate: function (message) {
            PyPoker.Player.resetControls();
            PyPoker.Player.resetTimers();

            switch (message.event) {
                case 'new-game':
                    PyPoker.Game.newGame(message);
                    break;
                case 'cards-assignment':
                    $cards = $('#current-player .cards');
                    $cards.empty();
                    for (i = 0; i < PyPoker.Game.numCards; i++) {
                        $cards.append($('<div class="card large" data-key="' + i + '"></div>'));
                    }
                    $('.card', $cards).click(function () {
                        if (PyPoker.Player.cardsChangeMode) {
                            $(this).toggleClass('selected');
                        }
                    });
                    PyPoker.Game.updateCurrentPlayerCards(message.cards, message.score);
                    break;
                case 'game-over':
                    PyPoker.Game.gameOver();
                    PyPoker.Game.updateRankingList();
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
                    PyPoker.Game.updatePlayersBet(); // Reset the bets
                    break;
                case 'player-action':
                    PyPoker.Player.onPlayerAction(message);
                    break;
                case 'dead-player':
                    PyPoker.Game.playerFold(message.player);
                    break;
                case 'cards-change':
                    PyPoker.Game.changeCards(message.player, message.num_cards);
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

        updateRankingList: function (message) {
            //message为有序的玩家数据元组列表 [(player_name, player_total_money, avg_profit), (player_name, player_total_money, avg_profit)]
            const rankingTableBody = document.querySelector('#ranking-table tbody');

            // 清空当前表格内容
            rankingTableBody.innerHTML = '';

            // 遍历 message 数据，填充表格行
            message.forEach((player, index) => {
                const [playerName, totalMoney, avgProfit, dailyProfit] = player;

                // 创建表格行
                const row = document.createElement('tr');

                // 填充表格列
                row.innerHTML = `
                    <td>${index + 1}</td> <!-- 排名 -->
                    <td>${playerName}</td> <!-- 玩家姓名 -->
                    <td>$${totalMoney}</td> <!-- 总金额 -->
                    <td>${avgProfit.toFixed(2)}</td> <!-- 平均收益 -->
                    <td>${dailyProfit.toFixed(2)}</td> <!-- mei日 -->
                `;

                // 添加行到表格
                rankingTableBody.appendChild(row);
            });
        },

        fetchRankingData: function () {
            const apiUrl = '/api/get-ranking'; // 后端 API 地址

            // 异步获取排行榜数据
            $.ajax({
                url: apiUrl,
                method: 'GET',
                dataType: 'json',
                success: function (data) {
                    if (data && Array.isArray(data)) {
                        // 调用 updateRankingList 更新表格
                        PyPoker.Game.updateRankingList(data);
                    } else {
                        console.error('Invalid ranking data received:', data);
                    }
                },
                error: function (xhr, status, error) {
                    console.error('Failed to fetch ranking data:', status, error);
                }
            });
        },
    },

    Logger: {
        log: function (text) {
            $p0 = $('#game-status p[data-key="0"]');
            $p1 = $('#game-status p[data-key="1"]');
            $p2 = $('#game-status p[data-key="2"]');
            $p3 = $('#game-status p[data-key="3"]');
            $p4 = $('#game-status p[data-key="4"]');

            $p4.text($p3.text());
            $p3.text($p2.text());
            $p2.text($p1.text());
            $p1.text($p0.text());
            $p0.text(text);
        }
    },

    Player: {
        betMode: false,

        cardsChangeMode: false,

        resetTimers: function () {
            // Reset timers
            $activeTimers = $('.timer.active');
            $activeTimers.TimeCircles().destroy();
            $activeTimers.removeClass('active');
        },

        resetControls: function () {
            // Reset controls
            PyPoker.Player.setCardsChangeMode(false);
            PyPoker.Player.disableBetMode();
        },

        sliderHandler: function (value) {
            if (value == 0) {
                $('#bet-cmd').attr("value", "Check");
            } else {
                $('#bet-cmd').attr("value", "$" + parseInt(value));
            }
            $('#bet-input').val(value);
        },

        enableBetMode: function (message) {
            PyPoker.Player.betMode = true;

            if (!message.min_score || $('#current-player').data('allowed-to-bet')) {
                // Set-up slider
                $('#bet-input').slider({
                    'min': parseInt(message.min_bet),
                    'max': parseInt(message.max_bet),
                    'value': parseInt(message.min_bet),
                    'formatter': PyPoker.Player.sliderHandler
                }).slider('setValue', parseInt(message.min_bet));

                // Fold control
                if (message.min_score) {
                    $('#fold-cmd').val('Pass')
                        .removeClass('btn-danger')
                        .addClass('btn-warning');
                } else {
                    $('#fold-cmd').val('Fold')
                        .addClass('btn-danger')
                        .removeClass('btn-warning');
                }

                $('#fold-cmd-wrapper').show();
                $('#bet-input-wrapper').show();
                $('#bet-cmd-wrapper').show();
                $('#no-bet-cmd-wrapper').hide();
            } else {
                $('#fold-cmd-wrapper').hide();
                $('#bet-input-wrapper').hide();
                $('#bet-cmd-wrapper').hide();
                $('#no-bet-cmd-wrapper').show();
            }

            $('#bet-controls').show();
        },

        enableBetModeNew: function (message) {
            PyPoker.Player.betMode = true;

            // 判断玩家是否允许下注
            if (!message.min_score || $('#current-player').data('allowed-to-bet')) {
                let minBet = parseInt(message.min_bet);
                let maxBet = parseInt(message.max_bet);
                let currentBet = minBet;

                const betAmountInput = $('#bet-input');
                const decreaseBetButton = $('#decrease-bet');
                const decreaseBetQuickButton = $('#decrease-bet-quick');
                const increaseBetButton = $('#increase-bet');
                const increaseBetQuickButton = $('#increase-bet-quick');
                const allinBetButton = $('#allin-bet');
                const betButton = $('#bet-cmd');
                allinBetButton.val(maxBet)

                // 更新下注显示
                function updateBetDisplay() {
                    betAmountInput.val(currentBet);
                    // 控制按钮状态
                    decreaseBetButton.prop('disabled', currentBet <= minBet);
                    decreaseBetQuickButton.prop('disabled', currentBet <= minBet);
                    increaseBetButton.prop('disabled', currentBet >= maxBet);
                    increaseBetQuickButton.prop('disabled', currentBet >= maxBet);
                    // 更新下注按钮显示
                    if (currentBet === 0) {
                        betButton.val('Check');
                    } else if (currentBet === minBet) {
                        betButton.val('Call')
                    } else if (currentBet === maxBet) {
                        betButton.val('All In');
                    } else {
                        betButton.val('Bet ' + currentBet);
                    }
                }

                // 初始化显示
                updateBetDisplay();

                // 增减下注金额
                decreaseBetButton.off('click').on('click', function () {
                    if (currentBet > minBet) {
                        currentBet = Math.max(minBet, currentBet - 10);
                        updateBetDisplay();
                    }
                });
                decreaseBetQuickButton.off('click').on('click', function () {
                    if (currentBet > minBet) {
                        currentBet = Math.max(minBet, currentBet - 50);
                        updateBetDisplay();
                    }
                });
                increaseBetButton.off('click').on('click', function () {
                    if (currentBet < maxBet) {
                        currentBet = Math.min(maxBet, currentBet + 10);
                        updateBetDisplay();
                    }
                });
                increaseBetQuickButton.off('click').on('click', function () {
                    if (currentBet < maxBet) {
                        currentBet = Math.min(maxBet, currentBet + 50);
                        updateBetDisplay();
                    }
                });
                // 弃牌控制
                if (message.min_score) {
                    $('#fold-cmd').val('Pass')
                        .removeClass('btn-danger')
                        .addClass('btn-warning');
                } else {
                    $('#fold-cmd').val('Fold')
                        .addClass('btn-danger')
                        .removeClass('btn-warning');
                }

                // 显示相关控件
                $('#fold-cmd-wrapper').show();
                $('#bet-input-wrapper').show();
                $('#bet-cmd-wrapper').show();
                $('#no-bet-cmd-wrapper').hide();
            } else {
                // 玩家不允许下注，隐藏控件
                $('#fold-cmd-wrapper').hide();
                $('#bet-input-wrapper').hide();
                $('#bet-cmd-wrapper').hide();
                $('#no-bet-cmd-wrapper').show();
            }

            $('#bet-controls').show();
        },

        disableBetMode: function () {
            $('#bet-controls').hide();
        },

        setCardsChangeMode: function (changeMode) {
            PyPoker.Player.cardsChangeMode = changeMode;

            if (changeMode) {
                $('#cards-change-controls').show();
            } else {
                $('#cards-change-controls').hide();
                $('#current-player .card.selected').removeClass('selected');
            }
        },

        onPlayerAction: function (message) {
            isCurrentPlayer = message.player.id == $('#current-player').attr('data-player-id');

            switch (message.action) {
                case 'bet':
                    if (isCurrentPlayer) {
                        PyPoker.Player.onBet(message);
                    }
                    break;
                case 'cards-change':
                    if (isCurrentPlayer) {
                        PyPoker.Player.onChangeCards(message);
                    }
                    break;
            }

            timeout = (Date.parse(message.timeout_date) - Date.now()) / 1000;

            $timers = $('.player[data-player-id=' + message.player.id + '] .timer');
            $timers.data('timer', timeout);
            $timers.TimeCircles({
                "start": true,
                "animation": "smooth",
                "bg_width": 1,
                "fg_width": 0.05,
                "count_past_zero": false,
                "time": {
                    "Days": {
                        show: false
                    },
                    "Hours": {
                        show: false
                    },
                    "Minutes": {
                        show: false
                    },
                    "Seconds": {
                        show: true
                    }
                }
            });
            $timers.addClass('active');
        },

        onBet: function (message) {
            // PyPoker.Player.enableBetMode(message);
            PyPoker.Player.enableBetModeNew(message)
            $("html, body").animate({
                scrollTop: $(document).height()
            }, "slow");
        },

        onChangeCards: function (message) {
            PyPoker.Player.setCardsChangeMode(true);
            $("html, body").animate({
                scrollTop: $(document).height()
            }, "slow");
        },

        toggleReadyStatus: function () {
            // 获取按钮和状态指示器元素
            const readyBtn = $('#ready-btn');
            const statusIndicator = $('#status-indicator');

            // 切换按钮的值和状态指示器的颜色
            if (readyBtn.val() === 'Ready') {
                readyBtn.val('Cancel'); // 按钮显示 "Cancel"
                statusIndicator.css('background-color', 'green'); // 指示器变为绿色
            } else {
                readyBtn.val('Ready'); // 按钮显示 "Ready"
                statusIndicator.css('background-color', 'red'); // 指示器变为红色
            }
        },

        // 检查 readyBtn 状态并将其传回后台
        checkReadyStateAndSend: function () {
            const readyBtn = $('#ready-btn');
            const isReady = readyBtn.val() === 'Cancel'; // 判断按钮状态是否为 "Cancel"

            // 构造消息
            const readyStateMessage = {
                message_type: 'ready-state-change',
                player_id: $('#current-player').attr('data-player-id'),
                ready: isReady
            };

            // 将消息发送到后台
            PyPoker.socket.emit('game_message', readyStateMessage);
        },
    },

    Room: {
        roomId: null,

        createPlayer: function (player = undefined) {
            if (player === undefined) {
                return $('<div class="player"><div class="player-info"></div></div>');
            }
            isCurrentPlayer = player.id == $('#current-player').attr('data-player-id');

            $playerName = $('<p class="player-name"></p>');
            $playerName.text(isCurrentPlayer ? 'You' : player.name);

            $playerMoney = $('<p class="player-money"></p>');
            $playerMoney.text('$' + parseInt(player.money));

            $playerInfo = $('<div class="player-info"></div>');
            $playerInfo.append($playerName);
            $playerInfo.append($playerMoney);

            $player = $('<div class="player' + (isCurrentPlayer ? ' current' : '') + '"></div>');
            $player.attr('data-player-id', player.id);
            $player.append($playerInfo);
            $player.append($('<div class="bet-wrapper"></div>'));
            $player.append($('<div class="cards"></div>'));
            $player.append($('<div class="timer"></div>'));

            return $player;
        },

        destroyRoom: function () {
            PyPoker.Game.gameOver();
            PyPoker.Room.roomId = null;
            $('#players').empty();
        },

        initRoom: function (message) {
            PyPoker.Room.roomId = message.room_id;
            // Initializing the room
            $('#players').empty();
            for (k in message.player_ids) {
                $seat = $('<div class="seat"></div>');
                $seat.attr('data-key', k);

                playerId = message.player_ids[k];

                if (playerId) {
                    // This seat is taken
                    $seat.append(PyPoker.Room.createPlayer(message.players[playerId]));
                    $seat.attr('data-player-id', playerId);
                } else {
                    $seat.append(PyPoker.Room.createPlayer());
                    $seat.attr('data-player-id', null);
                }
                $('#players').append($seat);
            }
        },

        onRoomUpdate: function (message) {
            //玩家更新时接受服务器消息
            if (PyPoker.Room.roomId == null) {
                PyPoker.Room.initRoom(message);
            }

            switch (message.event) {
                case 'player-added':
                    playerId = message.player_id;
                    player = message.players[playerId]
                    playerName = playerId == $('#current-player').attr('data-player-id') ? 'You' : player.name;
                    // Go through every available seat, find the one where the new player should sat and seated him
                    $('.seat').each(function () {
                        seat = $(this).attr('data-key');
                        if (message.player_ids[seat] == playerId) {
                            $(this).empty();
                            $(this).append(PyPoker.Room.createPlayer(player));
                            $(this).attr('data-player-id', playerId);
                            return;
                        }
                    });
                    break;

                case 'player-removed':
                    playerId = message.player_id;
                    playerName = $('.player[data-player-id=' + playerId + '] .player-name').text();
                    // Go through every available seat, find the one where the leaving player sat and kick him out
                    $('.seat').each(function () {
                        seatedPlayerId = $(this).attr('data-player-id');
                        if (seatedPlayerId == playerId) {
                            $(this).empty();
                            $(this).append(PyPoker.Room.createPlayer());
                            $(this).attr('data-player-id', null);
                            return;
                        }
                    });
                    break;
            }
        },
    },

    init: function () {
        PyPoker.socket = io();

        PyPoker.socket.on('connect', function () {
            PyPoker.Logger.log('Connected :)');
            PyPoker.socket.emit('join_game', {});
        });

        PyPoker.socket.on('disconnect', function () {
            PyPoker.Logger.log('Disconnected :(');
            PyPoker.Room.destroyRoom();
        });

        PyPoker.socket.on('game_connected', function (data) {
            PyPoker.onConnect(data);
        });

        PyPoker.socket.on('game_message', function (data) {
            console.log(data);

            switch (data.message_type) {
                case 'ping':
                    const readyBtn = $('#ready-btn');
                    const isReady = readyBtn.val() === 'Cancel';
                    PyPoker.socket.emit('game_message', {
                        'message_type': 'pong',
                        'ready': isReady
                    });
                    break;
                case 'room-update':
                    PyPoker.Room.onRoomUpdate(data);
                    break;
                case 'game-update':
                    PyPoker.Game.onGameUpdate(data);
                    break;
            }
        });

        PyPoker.socket.on('error', function (data) {
            PyPoker.Logger.log(data.error);
        });


        PyPoker.Game.fetchRankingData();

        // 准备按钮
        $('#ready-btn').click(function () {
            PyPoker.Player.toggleReadyStatus();
        });

        $('#cards-change-cmd').click(function () {
            discards = [];
            $('#current-player .card.selected').each(function () {
                discards.push($(this).data('key'))
            });
            PyPoker.socket.emit('game_message', {
                'message_type': 'cards-change',
                'cards': discards
            });
            PyPoker.Player.setCardsChangeMode(false);
        });

        $('#fold-cmd').click(function () {
            PyPoker.socket.emit('game_message', {
                'message_type': 'bet',
                'bet': -1
            });
            PyPoker.Player.disableBetMode();
        });

        $('#no-bet-cmd').click(function () {
            PyPoker.socket.emit('game_message', {
                'message_type': 'bet',
                'bet': 0
            });
            PyPoker.Player.disableBetMode();
        });

        $('#bet-cmd').click(function () {
            PyPoker.socket.emit('game_message', {
                'message_type': 'bet',
                'bet': $('#bet-input').val()
            });
            PyPoker.Player.disableBetMode();
        });

        $('#allin-bet').click(function () {
            PyPoker.socket.emit('game_message', {
                'message_type': 'bet',
                'bet': $('#allin-bet').val()
            });
            PyPoker.Player.disableBetMode();
        });

        PyPoker.Player.setCardsChangeMode(false);
        PyPoker.Player.disableBetMode();
    },

    onConnect: function (message) {
        PyPoker.Logger.log("Connection established with poker5 server: " + message.server_id);
        $('#current-player').attr('data-player-id', message.player.id);
    },

    onDisconnect: function (message) {

    },

    onError: function (message) {
        PyPoker.Logger.log(message.error);
    }
}

$(document).ready(function () {
    PyPoker.init();
})