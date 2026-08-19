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


def test_late_arrival_not_in_cohort_returns_none() -> None:
    ges.start_or_join(group_id=1, cell=(5, 5), cohort_ids={1, 2}, character_id=1)
    result = ges.start_or_join(group_id=1, cell=(5, 5), cohort_ids={1, 2, 3}, character_id=3)
    assert result is None
    # очередь не тронута
    queue = ges.get_queue(1)
    assert queue.cohort == {1, 2}


def test_cancel_removes_from_ready_and_cohort_without_resetting_others() -> None:
    ges.start_or_join(group_id=1, cell=(5, 5), cohort_ids={1, 2, 3}, character_id=1)
    ges.start_or_join(group_id=1, cell=(5, 5), cohort_ids={1, 2, 3}, character_id=2)
    ges.cancel(group_id=1, character_id=1)
    queue = ges.get_queue(1)
    assert queue.cohort == {2, 3}
    assert queue.ready == {2}  # участник 2 остаётся готов, не сброшен


def test_cancel_then_repress_is_treated_as_late_arrival() -> None:
    ges.start_or_join(group_id=1, cell=(5, 5), cohort_ids={1, 2}, character_id=1)
    ges.start_or_join(group_id=1, cell=(5, 5), cohort_ids={1, 2}, character_id=2)
    ges.cancel(group_id=1, character_id=1)
    # 1 передумал и снова жмёт "Исследовать" — но группа (2) уже "занята"
    result = ges.start_or_join(group_id=1, cell=(5, 5), cohort_ids={1, 2}, character_id=1)
    assert result is None


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
