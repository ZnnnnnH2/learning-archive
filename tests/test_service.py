from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from gomoku_display.framework import freeze_framework
from gomoku_display.service import TournamentService

SOURCE = Path("/Users/hanyuhe/Desktop/gomoku")


class ServiceTests(unittest.TestCase):
    def test_draw_creates_45_pairings_and_90_games(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            data = Path(temporary)
            freeze_framework(SOURCE, data)
            service = TournamentService(data)
            service.store.replace_roster([(f"2026{i:04d}", str(i)) for i in range(21)])
            for identifier in [row["student_id"] for row in service.store.players()]:
                source = data / f"{identifier}.cpp"; source.write_text("// mock")
                service.store.upsert_submission(identifier, str(source), identifier, "READY", binary_path=str(source))
            groups = service.draw(88)
            self.assertEqual({key: len(value) for key, value in groups.items()}, {"A": 6, "B": 5, "C": 5, "D": 5})
            state = service.store.state()
            self.assertEqual(len(state["games"]), 90)
            self.assertEqual(sum(1 for game in state["games"] if game["game_no"] == 1), 45)
            service.close()

    def test_finished_groups_promote_to_four_quarterfinals(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            data = Path(temporary); freeze_framework(SOURCE, data)
            service = TournamentService(data)
            service.store.replace_roster([(f"2026{i:04d}", str(i)) for i in range(21)])
            for identifier in [row["student_id"] for row in service.store.players()]:
                source = data / f"{identifier}.cpp"; source.write_text("// mock")
                service.store.upsert_submission(identifier, str(source), identifier, "READY", binary_path=str(source))
            service.draw(99)
            with service.store.connection:
                service.store.connection.execute("""UPDATE game SET status='FINISHED',result='BLACK_WIN',winner_id=black_id,
                    black_points=1,white_points=0""")
            self.assertEqual(service.advance_knockout(), "QUARTERFINALS_CREATED")
            qf_games = service.store.connection.execute("""SELECT COUNT(*) FROM game g JOIN pairing p ON p.id=g.pairing_id
                WHERE p.stage LIKE 'QF%'""").fetchone()[0]
            self.assertEqual(qf_games, 16)
            with service.store.connection:
                service.store.connection.execute("""UPDATE game SET status='FINISHED',result='DRAW',black_points=.5,white_points=.5
                    WHERE pairing_id IN (SELECT id FROM pairing WHERE stage LIKE 'QF%')""")
            self.assertEqual(service.advance_knockout(), "WAITING_FOR_QUARTERFINALS")
            self.assertEqual(service.store.connection.execute("""SELECT COUNT(*) FROM game g JOIN pairing p ON p.id=g.pairing_id
                WHERE p.stage LIKE 'QF%'""").fetchone()[0], 24)
            service.close()
