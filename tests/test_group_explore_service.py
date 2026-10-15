"""Групповое исследование (патч 51, ч.3): очередь готовности."""

from services import group_explore_service as ges


def teardown_function() -> None:
    ges._queues.clear()


def test_first_press_creates_queue_with_presser_ready() -> None:
    queue = ges.start_or_join(group_id=1, cell=(5, 5), cohort_ids={1, 2, 3}, character_id=1)
    assert queue is not None
    assert queue.ready == {1}
    assert queue.cohort == {1, 2, 3}
    assert ges.is_ready_to_start(queue) is False


def test_second_press_from_cohort_joins_same_queue() -> None:
    ges.start_or_join(group_id=1, cell=(5, 5), cohort_ids={1, 2, 3}, character_id=1)
    queue = ges.start_or_join(group_id=1, cell=(5, 5), cohort_ids={1, 2, 3}, character_id=2)
    assert queue.ready == {1, 2}


def test_ready_when_all_cohort_pressed() -> None:
    ges.start_or_join(group_id=1, cell=(5, 5), cohort_ids={1, 2}, character_id=1)
    queue = ges.start_or_join(group_id=1, cell=(5, 5), cohort_ids={1, 2}, character_id=2)
    assert ges.is_ready_to_start(queue) is True


def test_late_arrival_who_presses_joins_without_blocking_others() -> None:
    ges.start_or_join(group_id=1, cell=(5, 5), cohort_ids={1, 2}, character_id=1)
    queue = ges.start_or_join(group_id=1, cell=(5, 5), cohort_ids={1, 2, 3}, character_id=3)
    assert queue.cohort == {1, 2, 3}
    assert queue.ready == {1, 3}


def test_cancel_removes_from_ready_and_cohort_without_resetting_others() -> None:
    ges.start_or_join(group_id=1, cell=(5, 5), cohort_ids={1, 2, 3}, character_id=1)
    ges.start_or_join(group_id=1, cell=(5, 5), cohort_ids={1, 2, 3}, character_id=2)
    ges.cancel(group_id=1, character_id=1)
    queue = ges.get_queue(1)
    assert queue.cohort == {2, 3}
    assert queue.ready == {2}  # участник 2 остаётся готов, не сброшен


def test_cancel_then_repress_rejoins() -> None:
    ges.start_or_join(group_id=1, cell=(5, 5), cohort_ids={1, 2, 3}, character_id=1)
    ges.cancel(group_id=1, character_id=1)
    queue = ges.start_or_join(group_id=1, cell=(5, 5), cohort_ids={1, 2, 3}, character_id=1)
    assert queue.ready == {1}
    assert 1 in queue.cohort


def test_cancel_reports_ready_players_when_queue_completes_without_leaver() -> None:
    ges.start_or_join(group_id=1, cell=(5, 5), cohort_ids={1, 2, 3}, character_id=1)
    ges.start_or_join(group_id=1, cell=(5, 5), cohort_ids={1, 2, 3}, character_id=2)
    assert ges.cancel(group_id=1, character_id=3) == {1, 2}
    assert ges.cancel(group_id=1, character_id=2) == {1}


def test_incident_member_left_group_does_not_block_the_rest() -> None:
    """2026-10-12: К и Р готовы, Т (сеть упала) вышел из группы, К отменил и
    нажал снова. Раньше очередь ждала ушедшего Т, а К получал «группа уже в
    деле». Теперь кохорт сверяется с группой при нажатии."""
    k, r, t = 7, 59, 55
    ges.start_or_join(group_id=1, cell=(17, -14), cohort_ids={k, r, t}, character_id=k)
    ges.start_or_join(group_id=1, cell=(17, -14), cohort_ids={k, r, t}, character_id=r)
    # Т вышел из группы - на клетке в группе теперь двое
    queue = ges.start_or_join(group_id=1, cell=(17, -14), cohort_ids={k, r}, character_id=k)
    assert queue.cohort == {k, r}
    assert ges.is_ready_to_start(queue)


def test_queue_on_another_cell_starts_fresh() -> None:
    ges.start_or_join(group_id=1, cell=(5, 5), cohort_ids={1, 2}, character_id=1)
    queue = ges.start_or_join(group_id=1, cell=(6, 5), cohort_ids={1, 2}, character_id=2)
    assert queue.cell == (6, 5)
    assert queue.ready == {2}


def test_cancel_by_sole_cohort_member_clears_queue() -> None:
    ges.start_or_join(group_id=1, cell=(5, 5), cohort_ids={1}, character_id=1)
    ges.cancel(group_id=1, character_id=1)
    assert ges.get_queue(1) is None
    assert ges.is_queued(1) is False


def test_cancel_by_every_cohort_member_clears_queue() -> None:
    ges.start_or_join(group_id=1, cell=(5, 5), cohort_ids={1, 2}, character_id=1)
    ges.cancel(group_id=1, character_id=1)
    ges.cancel(group_id=1, character_id=2)
    assert ges.get_queue(1) is None


def test_ready_to_start_false_for_empty_cohort() -> None:
    queue = ges.ReadyQueue(group_id=1, cell=(0, 0), cohort=set())
    assert ges.is_ready_to_start(queue) is False


def test_co_located_members_filters_by_position() -> None:
    class M:
        def __init__(self, id_, x, y):
            self.id = id_
            self.pos_x = x
            self.pos_y = y

    members = [M(1, 5, 5), M(2, 5, 5), M(3, 6, 5)]
    result = ges.co_located_members(members, 5, 5)
    assert {m.id for m in result} == {1, 2}


def test_queue_without_ready_members_is_rebuilt_for_whole_cell() -> None:
    """Репорт 2026-10-14: B нажал «Исследовать», потом сел отдыхать (отмена
    убрала его из очереди). A нажал - и ушёл один, а B после отдыха ждал A.
    Теперь пустая по готовности очередь собирается заново на всех."""
    gid = 990001
    ges.clear(gid)
    ges.start_or_join(gid, (1, 1), {1, 2}, 2)
    ges.cancel(gid, 2)
    queue = ges.start_or_join(gid, (1, 1), {1, 2}, 1)
    assert queue.cohort == {1, 2} and not ges.is_ready_to_start(queue)
    queue = ges.start_or_join(gid, (1, 1), {1, 2}, 2)
    assert ges.is_ready_to_start(queue)
    ges.clear(gid)
