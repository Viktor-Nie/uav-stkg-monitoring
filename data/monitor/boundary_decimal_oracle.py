"""Independent full-witness Decimal reference; never imports the FIFO monitor."""
from decimal import Decimal as D


def evaluate(points, rule, contract):
    times = [D(p['time']) for p in points]
    values = [D(p['value']) for p in points]
    eps = D(contract['timestamp_epsilon'])
    gap = D(contract['maximum_gap'])
    empty = {'invariant_verdict': 'rejected_input_contract', 'invariant_violations': [],
             'response_verdict': 'rejected_input_contract', 'triggers': [],
             'recovered': [], 'expired': [], 'pending': []}
    if (len(points) < 2 or not all(x.is_finite() for x in times + values)
            or any(b-a <= eps or b-a > gap+eps for a,b in zip(times,times[1:]))):
        return empty
    upper = D(rule['upper']) + D(rule['value_epsilon'])
    recovery = D(rule['recovery']) + D(rule['value_epsilon'])
    dwell, duration = D(rule['dwell']), D(rule['deadline'])
    violations = [i for i,v in enumerate(values) if v > upper]
    recovered, expired, pending = [], [], []
    # Each trigger gets its own independently rescanned future witness search.
    # No shared queue, recovery state, or production output supplies truth.
    for oid,i in enumerate(violations):
        due = times[i]+duration
        start = None
        witness = False
        for j in range(i+1,len(times)):
            if times[j] > due+eps:
                break
            if values[j] <= recovery:
                if start is None:
                    start = times[j]
                if times[j]-start >= dwell-eps:
                    witness = True
                    break
            else:
                start = None
        if witness:
            recovered.append(oid)
        elif times[-1] > due+eps:
            expired.append(oid)
        else:
            pending.append(oid)
    verdict = 'violated' if expired else 'inconclusive_end_of_trace' if pending else 'satisfied'
    return {'invariant_verdict': 'violated' if violations else 'satisfied',
            'invariant_violations': violations, 'response_verdict': verdict,
            'triggers': violations, 'recovered': recovered,
            'expired': expired, 'pending': pending}
