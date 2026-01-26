from .config import INIT_MONEY


class Player:
    def __init__(self, id, name, money, avatar=None, ready=False):
        self._id = id
        self._name = name
        self._money = money
        self._avatar = avatar
        self.seat = None
        self._ready = ready

    @property
    def id(self) -> int:
        return self._id

    @property
    def name(self) -> str:
        return self._name

    @property
    def money(self) -> float:
        return self._money

    @property
    def ready(self) -> bool:
        return self._ready

    @property
    def avatar(self) -> str:
        return self._avatar

    def dto(self):
        return {
            "id": self.id,
            "name": self.name,
            "money": self.money,
            "avatar": self.avatar,
        }

    def take_money(self, money: float):
        if money > self._money:
            raise ValueError("Player does not have enough money")
        if money < 0.0:
            raise ValueError("Money has to be a positive amount")
        self._money -= money

    def add_money(self, money: float):
        if money <= 0.0:
            raise ValueError("Money has to be a positive amount")
        self._money += money

    def add_loan(self):
        self.add_money(INIT_MONEY)

    def sync_from_database(self):
        """
        Sync player data (money and avatar) from the database.
        """
        try:
            # Avoid circular import if any, do local import
            from poker.db_utils import get_player_by_id
            
            player_data = get_player_by_id(self._id)
            if player_data:
                # 'chips' in wallet table maps to money
                if player_data.get('chips') is not None:
                    self._money = float(player_data['chips'])
                
                # 'avatar' in players table
                if player_data.get('avatar') is not None:
                    self._avatar = str(player_data['avatar'])
                    
        except Exception as e:
            print(f"Error syncing player {self._name} data from database: {e}")

    def __str__(self):
        return "player {}".format(self._id)
