"""Orthogonal drawing-space search. Coordinates never enter the physical router."""
import heapq


def simplify(points):
    result=[]
    for p in points:
        if result and p==result[-1]: continue
        if len(result)>1 and (result[-2][0]==result[-1][0]==p[0] or result[-2][1]==result[-1][1]==p[1]): result.pop()
        result.append(p)
    return result


def orthogonal_route(start, goal, obstacles, tracks=(), occupied=()):
    xs=sorted({start[0],goal[0],*(r[0]-12 for r in obstacles),*(r[2]+12 for r in obstacles)})
    ys=sorted({start[1],goal[1],*tracks,*(r[1]-12 for r in obstacles),*(r[3]+12 for r in obstacles)})
    occupied_rows={};occupied_columns={}
    for a,b in occupied:
        if a[0]==b[0]:occupied_columns.setdefault(a[0],[]).append(sorted((a[1],b[1])))
        elif a[1]==b[1]:occupied_rows.setdefault(a[1],[]).append(sorted((a[0],b[0])))
    def clear(a,b):
        if a[0]==b[0]: return not any(x0<a[0]<x1 and max(min(a[1],b[1]),y0)<min(max(a[1],b[1]),y1) for x0,y0,x1,y1 in obstacles)
        return not any(y0<a[1]<y1 and max(min(a[0],b[0]),x0)<min(max(a[0],b[0]),x1) for x0,y0,x1,y1 in obstacles)
    source=(xs.index(start[0]),ys.index(start[1]),-1);queue=[(0,0,source)];cost={source:0};parent={source:None}
    while queue:
        _,distance,state=heapq.heappop(queue)
        if distance!=cost[state]:continue
        x,y,d=state;a=(xs[x],ys[y])
        if a==goal:
            path=[]
            while state is not None:
                path.append((xs[state[0]],ys[state[1]]));state=parent[state]
            return simplify(list(reversed(path)))
        for dx,dy,axis in ((1,0,0),(-1,0,0),(0,1,1),(0,-1,1)):
            xx,yy=x+dx,y+dy
            if not (0<=xx<len(xs) and 0<=yy<len(ys)):continue
            b=(xs[xx],ys[yy])
            if not clear(a,b):continue
            # Coincident segments cost more than crossings. Neither implies connectivity.
            intervals=occupied_columns.get(a[0],[]) if axis==1 else occupied_rows.get(a[1],[])
            lo,hi=sorted((a[1],b[1]) if axis==1 else (a[0],b[0]))
            congestion=sum(100 for low,high in intervals if max(lo,low)<min(hi,high))
            score=distance+abs(a[0]-b[0])+abs(a[1]-b[1])+(18 if d!=-1 and axis!=d else 0)+congestion
            next_state=(xx,yy,axis)
            if score<cost.get(next_state,float('inf')):
                cost[next_state]=score;parent[next_state]=state
                heapq.heappush(queue,(score+abs(b[0]-goal[0])+abs(b[1]-goal[1]),score,next_state))
    raise ValueError('No orthogonal drawing path avoids symbol/label obstacles.')
