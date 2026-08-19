CHART_JAVASCRIPT = r"""
(() => {
  'use strict';
  const script = document.currentScript;
  const reportId = script && script.dataset.report;
  if (!reportId) return;
  const ns = 'http://www.w3.org/2000/svg';
  const svgNode = (name, attrs = {}) => {
    const node = document.createElementNS(ns, name);
    Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, String(value)));
    return node;
  };
  const finite = value => typeof value === 'number' && Number.isFinite(value);
  const tooltip = document.getElementById('chart-tooltip');
  const showTip = (event, text) => {
    tooltip.textContent = text;
    tooltip.style.left = `${event.clientX + 12}px`;
    tooltip.style.top = `${event.clientY + 12}px`;
    tooltip.hidden = false;
  };
  const hideTip = () => { tooltip.hidden = true; };

  function renderChart(host, chart, lifestyle) {
    const width = 720, height = 260, pad = 36;
    const values = chart.series.flatMap(item => item.values).filter(finite);
    if (!values.length) { host.textContent = 'No chart data'; return; }
    let low = Math.min(...values), high = Math.max(...values);
    if (low === high) { low -= 1; high += 1; }
    const svg = svgNode('svg', {viewBox:`0 0 ${width} ${height}`, 'aria-hidden':'true'});
    svg.append(svgNode('line', {x1:pad,y1:height-pad,x2:width-pad,y2:height-pad,class:'axis'}));
    chart.series.forEach((series, seriesIndex) => {
      const group = svgNode('g', {'data-series':seriesIndex});
      const points = [];
      series.values.forEach((value, index) => {
        if (!finite(value)) return;
        const x = chart.labels.length < 2 ? width / 2 : pad + index * (width - pad * 2) / (chart.labels.length - 1);
        const y = height - pad - (value - low) * (height - pad * 2) / (high - low);
        points.push(`${x},${y}`);
        const circle = svgNode('circle', {cx:x,cy:y,r:4,fill:series.color,tabindex:0});
        const label = `${chart.labels[index]} - ${series.name}: ${value}`;
        circle.addEventListener('pointermove', event => showTip(event, label));
        circle.addEventListener('pointerleave', hideTip);
        circle.addEventListener('focus', () => { tooltip.textContent = label; tooltip.hidden = false; });
        circle.addEventListener('blur', hideTip);
        group.append(circle);
      });
      if (points.length > 1) group.prepend(svgNode('polyline', {points:points.join(' '),fill:'none',stroke:series.color,'stroke-width':3}));
      svg.append(group);
    });
    lifestyle.forEach(item => {
      const index = chart.labels.findIndex(label => label.startsWith(item.date));
      if (index < 0 || chart.labels.length < 2) return;
      const x = pad + index * (width - pad * 2) / (chart.labels.length - 1);
      const marker = svgNode('line', {
        x1:x,y1:pad,x2:x,y2:height-pad,class:'lifestyle-marker',tabindex:0
      });
      const label = `${item.date} - Lifestyle: ${item.name}`;
      marker.addEventListener('pointermove', event => showTip(event, label));
      marker.addEventListener('pointerleave', hideTip);
      marker.addEventListener('focus', () => {
        tooltip.textContent = label; tooltip.hidden = false;
      });
      marker.addEventListener('blur', hideTip);
      svg.append(marker);
    });
    const legend = document.createElement('div'); legend.className = 'chart-legend';
    chart.series.forEach((series, index) => {
      const button = document.createElement('button');
      button.type = 'button'; button.textContent = series.name; button.style.borderColor = series.color;
      button.setAttribute('aria-pressed', 'true');
      button.addEventListener('click', () => {
        const group = svg.querySelector(`[data-series="${index}"]`);
        const visible = button.getAttribute('aria-pressed') === 'true';
        button.setAttribute('aria-pressed', String(!visible));
        group.style.display = visible ? 'none' : '';
      });
      legend.append(button);
    });
    host.replaceChildren(svg, legend);
  }

  function renderRoute(host, route, tilesEnabled) {
    const width = 720, height = 300, pad = 20;
    if (!route.points.length) { host.textContent = 'No route data'; return; }
    const lats = route.points.map(point => point[0]), lons = route.points.map(point => point[1]);
    const minLat=Math.min(...lats), maxLat=Math.max(...lats), minLon=Math.min(...lons), maxLon=Math.max(...lons);
    const svg=svgNode('svg',{viewBox:`0 0 ${width} ${height}`});
    let points;
    if (tilesEnabled) {
      const span = Math.max(maxLat-minLat, maxLon-minLon);
      const zoom = span < .01 ? 15 : span < .03 ? 14 : span < .08 ? 13 : span < .2 ? 12 : 10;
      const scale = 256 * 2 ** zoom;
      const worldX = lon => (lon + 180) / 360 * scale;
      const worldY = lat => {
        const safe = Math.max(-85.0511, Math.min(85.0511, lat));
        const rad = safe * Math.PI / 180;
        return (1 - Math.asinh(Math.tan(rad)) / Math.PI) / 2 * scale;
      };
      const centerX = worldX((minLon + maxLon) / 2);
      const centerY = worldY((minLat + maxLat) / 2);
      const left = centerX - width / 2, top = centerY - height / 2;
      const tileGroup = svgNode('g', {class:'map-tiles'});
      const count = 2 ** zoom;
      for (let tx=Math.floor(left/256); tx<=Math.floor((left+width)/256); tx += 1) {
        for (let ty=Math.floor(top/256); ty<=Math.floor((top+height)/256); ty += 1) {
          if (ty < 0 || ty >= count) continue;
          const wrappedX = ((tx % count) + count) % count;
          tileGroup.append(svgNode('image', {
            href:`https://tile.openstreetmap.org/${zoom}/${wrappedX}/${ty}.png`,
            x:tx*256-left,y:ty*256-top,width:256,height:256
          }));
        }
      }
      svg.append(tileGroup);
      points=route.points.map(([lat,lon]) => `${worldX(lon)-left},${worldY(lat)-top}`).join(' ');
    } else {
      const latSpan=maxLat-minLat||1, lonSpan=maxLon-minLon||1;
      points=route.points.map(([lat,lon]) => `${pad+(lon-minLon)*(width-pad*2)/lonSpan},${height-pad-(lat-minLat)*(height-pad*2)/latSpan}`).join(' ');
    }
    svg.append(svgNode('polyline',{points,fill:'none',stroke:'#4776E6','stroke-width':4,'stroke-linecap':'round','stroke-linejoin':'round'}));
    if (tilesEnabled) {
      const attribution = document.createElement('p');
      attribution.className = 'map-attribution';
      const link = document.createElement('a');
      link.href = 'https://www.openstreetmap.org/copyright';
      link.target = '_blank'; link.rel = 'noreferrer noopener';
      link.textContent = '© OpenStreetMap contributors';
      attribution.append(link);
      host.replaceChildren(svg, attribution);
    } else {
      host.replaceChildren(svg);
    }
  }

  fetch(`/weekly-report/${encodeURIComponent(reportId)}/data`, {credentials:'same-origin'})
    .then(response => { if (!response.ok) throw new Error('Report data unavailable'); return response.json(); })
    .then(data => {
      const charts = new Map(data.charts.map(item => [item.id, item]));
      document.querySelectorAll('[data-chart]').forEach(host => { const chart=charts.get(host.dataset.chart); if(chart) renderChart(host,chart,data.lifestyle); });
      const routes = new Map(data.routes.map(item => [item.id, item]));
      document.querySelectorAll('[data-route]').forEach(host => { const route=routes.get(host.dataset.route); if(route) renderRoute(host,route,data.map_tiles_enabled); });
    })
    .catch(() => document.querySelectorAll('.interactive-chart,.route-chart').forEach(host => { host.textContent='Interactive data unavailable; tables remain available.'; }));
})();
"""
