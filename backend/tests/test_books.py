from app.books import pricing_books, shown


def test_offshore_books_drop_out_only_when_hidden():
    every = ["Bovada", "DraftKings", "FanDuel"]
    assert shown(every, False) == every and shown(every, True) == ["DraftKings", "FanDuel"]
    assert pricing_books(None, every, False) is None and pricing_books("Bovada", every, False) == "Bovada"
    assert pricing_books(None, every, True) == "DraftKings,FanDuel"
    assert pricing_books("Bovada,FanDuel", every, True) == "FanDuel"
    assert pricing_books("Bovada", every, True) == "none"
