from __future__ import annotations


DIAGRAM_TIKZ_MACROS = r"""
\definecolor{edu-diagram-ink}{RGB}{17,24,39}
\definecolor{edu-diagram-marker}{RGB}{220,38,38}
\definecolor{edu-diagram-angle}{RGB}{5,150,105}
\tikzset{
  diagram point/.style={fill=edu-diagram-ink},
  diagram tick/.style={draw=edu-diagram-marker,line width=0.9pt,line cap=round},
  diagram segment/.style={draw=edu-diagram-ink,line cap=round},
  point label/.style={inner sep=1pt},
  condition label/.style={inner sep=1pt}
}
\providecommand{\DrawSegment}[3][]{\draw[diagram segment,#1] (#2) -- (#3);}
\providecommand{\DrawDashedSegment}[3][]{\draw[diagram segment,dashed,#1] (#2) -- (#3);}
\providecommand{\Triangle}[4][]{\path[#1] (#2) -- (#3) -- (#4) -- cycle;}
\providecommand{\Quadrilateral}[5][]{\path[#1] (#2) -- (#3) -- (#4) -- (#5) -- cycle;}
\providecommand{\PolygonPath}[2][]{\path[#1] #2 -- cycle;}
\providecommand{\DiagramPointRadius}{0.052cm}
\providecommand{\PointDot}[2][]{\fill[diagram point,#1] (#2) circle[radius=\DiagramPointRadius];}
\providecommand{\PointLabel}[3][]{\node[point label,#1] at (#2) {#3};}
\providecommand{\SegmentLabel}[4][]{\node[condition label,#1] at ($(#2)!0.5!(#3)$) {#4};}
\providecommand{\CoordinateTag}[3][]{\node[condition label,#1] at (#2) {#3};}
\providecommand{\AngleMark}[4][]{\pic[draw=edu-diagram-angle,line width=0.9pt,angle radius=0.48cm,#1] {angle=#2--#3--#4};}
\providecommand{\AngleLabel}[5][]{\pic["{#5}",draw=none,angle radius=0.64cm,#1] {angle=#2--#3--#4};}
\providecommand{\RightAngleMark}[4][]{\pic[draw=edu-diagram-marker,line width=0.9pt,angle radius=0.28cm,#1] {right angle=#2--#3--#4};}
\providecommand{\EqualTick}[3][]{%
  \path[postaction={decorate},decoration={markings,mark=at position .5 with {\draw[diagram tick,#1] (0pt,-4pt) -- (0pt,4pt);}}] (#2) -- (#3);%
}
\providecommand{\DoubleEqualTick}[3][]{%
  \path[postaction={decorate},decoration={markings,mark=at position .46 with {\draw[diagram tick,#1] (0pt,-4pt) -- (0pt,4pt);},mark=at position .54 with {\draw[diagram tick,#1] (0pt,-4pt) -- (0pt,4pt);}}] (#2) -- (#3);%
}
\providecommand{\TripleEqualTick}[3][]{%
  \path[postaction={decorate},decoration={markings,mark=at position .43 with {\draw[diagram tick,#1] (0pt,-4pt) -- (0pt,4pt);},mark=at position .5 with {\draw[diagram tick,#1] (0pt,-4pt) -- (0pt,4pt);},mark=at position .57 with {\draw[diagram tick,#1] (0pt,-4pt) -- (0pt,4pt);}}] (#2) -- (#3);%
}
\providecommand{\ParallelMark}[3][]{\EqualTick[#1]{#2}{#3}}
\providecommand{\NamedSegmentPath}[3]{\path[name path=#1] (#2) -- (#3);}
\providecommand{\IntersectPaths}[3]{\path[name intersections={of=#2 and #3, by=#1}];}
""".strip()
