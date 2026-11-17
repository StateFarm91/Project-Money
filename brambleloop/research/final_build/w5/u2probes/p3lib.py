from brambleloop.cir.model import Row, Op
def rows_from(counts):
    rows=[]
    for i,n in enumerate(counts):
        prev = counts[i-1] if i else 0
        if i==0: ops=[Op("sc",n)]
        elif n>prev: ops=[Op("inc",n-prev)]+([Op("sc",2*prev-n)] if 2*prev>n else [])
        elif n<prev: ops=[Op("dec",prev-n)]+([Op("sc",2*n-prev)] if 2*n>prev else [])
        else: ops=[Op("sc",n)]
        rows.append(Row(index=i+1, ops=ops, declared_count=n, turning_chain=0))
    return rows
