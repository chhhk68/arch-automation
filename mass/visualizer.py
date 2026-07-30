"""plotly 기반 3D mass 시각화 — SketchUp과 동일한 마우스 조작"""

import plotly.graph_objects as go
from .regulations import FLOOR_HEIGHT


def _box_traces(x0, y0, z0, w, d, h, color, opacity=0.75, name=""):
    """직육면체를 Mesh3d trace로 반환"""
    x1, y1, z1 = x0 + w, y0 + d, z0 + h
    vx = [x0, x1, x1, x0, x0, x1, x1, x0]
    vy = [y0, y0, y1, y1, y0, y0, y1, y1]
    vz = [z0, z0, z0, z0, z1, z1, z1, z1]
    # 12개 삼각형 면
    i = [0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 0, 0]
    j = [1, 2, 2, 5, 3, 6, 0, 7, 5, 6, 3, 4]
    k = [2, 3, 5, 6, 6, 7, 7, 4, 6, 7, 7, 5]
    return go.Mesh3d(
        x=vx, y=vy, z=vz,
        i=i, j=j, k=k,
        color=color,
        opacity=opacity,
        name=name,
        showlegend=bool(name),
        flatshading=True,
        lighting=dict(ambient=0.7, diffuse=0.8, specular=0.2),
    )


def _floor_color(floor_idx: int, total: int) -> str:
    """층수에 따라 파란 계열 색상 반환"""
    t = floor_idx / max(total - 1, 1)
    r = int(40 + t * 30)
    g = int(100 + t * 80)
    b = int(200 + t * 40)
    return f"rgb({r},{g},{b})"


def plot_mass(site, footprints: list, result_summary: str):
    """
    SketchUp과 동일한 마우스 조작:
      - 왼쪽 버튼 드래그  : 궤도 회전 (Orbit)
      - 오른쪽 버튼 드래그: 이동 (Pan)
      - 스크롤            : 확대/축소 (Zoom)
    """
    traces = []

    # ── 대지 바닥 ─────────────────────────────────────────────
    sx, sy = site.width, site.depth
    traces.append(go.Mesh3d(
        x=[0, sx, sx, 0],
        y=[0, 0, sy, sy],
        z=[0, 0, 0, 0],
        i=[0], j=[1], k=[2],
        color="rgb(60,120,80)", opacity=0.4,
        name="대지", showlegend=True,
    ))
    traces.append(go.Mesh3d(
        x=[0, sx, 0],
        y=[0, sy, sy],
        z=[0, 0, 0],
        i=[0], j=[1], k=[2],
        color="rgb(60,120,80)", opacity=0.4,
        showlegend=False,
    ))

    # ── 층별 mass ─────────────────────────────────────────────
    n = len(footprints)
    for idx, (x0, y0, w, d) in enumerate(footprints):
        z0 = idx * FLOOR_HEIGHT
        color = _floor_color(idx, n)
        traces.append(_box_traces(
            x0, y0, z0, w, d, FLOOR_HEIGHT,
            color=color, opacity=0.8,
            name=f"{idx+1}F ({w:.1f}×{d:.1f}m)",
        ))

    # ── 이격거리 선 ───────────────────────────────────────────
    sn, ss, se, sw = site.setback_n, site.setback_s, site.setback_e, site.setback_w
    bx = [sw, sx-se, sx-se, sw, sw]
    by = [ss, ss, sy-sn, sy-sn, ss]
    traces.append(go.Scatter3d(
        x=bx, y=by, z=[0]*5,
        mode="lines",
        line=dict(color="yellow", width=3, dash="dot"),
        name="이격거리", showlegend=True,
    ))

    # ── 북쪽 화살표 ───────────────────────────────────────────
    traces.append(go.Scatter3d(
        x=[sx/2, sx/2], y=[sy*0.85, sy*1.1],
        z=[0, 0],
        mode="lines+text",
        line=dict(color="red", width=4),
        text=["", "N"],
        textfont=dict(color="red", size=14),
        name="북", showlegend=False,
    ))

    # ── 법규 검토 텍스트 (annotation) ─────────────────────────
    summary_html = result_summary.replace("\n", "<br>")

    total_h = n * FLOOR_HEIGHT
    fig = go.Figure(data=traces)
    fig.update_layout(
        title=dict(
            text=f"3D Mass Study — {n}층 / {total_h:.0f}m",
            font=dict(size=16, color="white"),
        ),
        paper_bgcolor="#1a1a2e",
        scene=dict(
            bgcolor="#0d0d1a",
            xaxis=dict(title="동→서 (m)", color="white", gridcolor="#334"),
            yaxis=dict(title="남→북 (m)", color="white", gridcolor="#334"),
            zaxis=dict(title="높이 (m)",  color="white", gridcolor="#334"),
            aspectmode="data",
            camera=dict(
                eye=dict(x=1.5, y=-1.8, z=1.2),
                up=dict(x=0, y=0, z=1),
            ),
        ),
        legend=dict(
            font=dict(color="white"),
            bgcolor="rgba(20,20,40,0.8)",
        ),
        annotations=[dict(
            text=summary_html,
            xref="paper", yref="paper",
            x=1.02, y=0.98,
            xanchor="left", yanchor="top",
            showarrow=False,
            font=dict(family="monospace", size=11, color="#ccccff"),
            bgcolor="rgba(10,10,30,0.85)",
            bordercolor="#445",
            borderwidth=1,
        )],
        margin=dict(r=320),
    )

    # ── 드래그 모드: orbit (SketchUp 기본과 동일) ─────────────
    fig.update_layout(
        scene_dragmode="orbit",   # 왼쪽 드래그 = 궤도 회전
    )

    fig.show()
