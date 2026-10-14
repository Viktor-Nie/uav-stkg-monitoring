"""Historical stratified split count rule."""

def allocate_counts(case_count: int, validation_ratio: float, test_ratio: float) -> tuple[int, int, int]:
    """Return train/validation/test counts while keeping every split non-empty.

    Every class-status stratum in the verified package has at least six cases.
    The guard still makes the script safe if a future subset has fewer cases.
    """
    if case_count < 3:
        return case_count, 0, 0
    validation_count = max(1, int(round(case_count * validation_ratio)))
    test_count = max(1, int(round(case_count * test_ratio)))
    while validation_count + test_count >= case_count:
        if validation_count >= test_count and validation_count > 1:
            validation_count -= 1
        elif test_count > 1:
            test_count -= 1
        else:
            break
    return case_count - validation_count - test_count, validation_count, test_count
