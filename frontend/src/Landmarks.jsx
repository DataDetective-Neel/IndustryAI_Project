import React from 'react';

export default function Landmarks({points=[], width, height, verified=false}) {
  const radius = Math.max(width,height)/70;
  return <g className="landmark-markers" data-verification={verified ? 'verified' : 'tentative'}>
    {points.length === 4 && points.map(([x,y],i) => Number.isFinite(x) && Number.isFinite(y) &&
      <g key={i} data-landmark-id={`L${i}`}>
        <circle cx={x} cy={y} r={radius} fill={verified ? '#087e78' : '#87500b'} stroke="white" strokeWidth="3" strokeDasharray={verified ? undefined : '5 3'} />
        <text x={x} y={y} textAnchor="middle" dominantBaseline="central" fill="white" fontSize={radius}>{`L${i}`}</text>
      </g>)}
  </g>;
}
