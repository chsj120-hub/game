shader_type canvas_item;
// 24절기·날씨·낮밤 환경 오버레이 (완전판 1.1)
// season 0봄 1여름 2가을 3겨울 / weather 0맑음 1비 2폭풍우 3눈 4안개 / night 0~1(해질녘 보간)

uniform int season = 0;
uniform int weather = 0;
uniform float night = 0.0;
uniform float term_progress = 0.0;
uniform float intensity : hint_range(0.0, 1.0) = 0.6;
uniform float aspect = 2.6667;

float hash(vec2 p) { return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }

float noise(vec2 p) {
	vec2 i = floor(p); vec2 f = fract(p); vec2 u = f * f * (3.0 - 2.0 * f);
	return mix(mix(hash(i), hash(i + vec2(1, 0)), u.x), mix(hash(i + vec2(0, 1)), hash(i + vec2(1, 1)), u.x), u.y);
}

vec3 season_tint(int s) {
	if (s == 0) return vec3(1.0, 0.93, 0.95);
	if (s == 1) return vec3(0.88, 0.97, 0.9);
	if (s == 2) return vec3(1.0, 0.88, 0.72);
	return vec3(0.86, 0.9, 1.0);
}

float particles(vec2 uv, float t, float scale, vec2 dir, float size_) {
	vec2 p = uv * scale + dir * t;
	vec2 cell = floor(p);
	vec2 f = fract(p) - 0.5;
	float r = hash(cell);
	vec2 off = vec2(hash(cell + 3.1), hash(cell + 7.7)) - 0.5;
	return step(0.55, r) * smoothstep(size_, size_ * 0.3, length(f - off * 0.6));
}

float rain(vec2 uv, float t, float density, float slant) {
	vec2 p = vec2(uv.x * 90.0 + uv.y * slant, uv.y * 6.0 - t * 6.0);
	return step(density, hash(floor(p))) * smoothstep(0.0, 0.5, fract(p.y));
}

void fragment() {
	vec2 uv = UV;
	vec2 ua = vec2(uv.x * aspect, uv.y);
	float t = TIME;
	vec3 tint = mix(season_tint(season), season_tint((season + 1) % 4), term_progress * 0.35);
	float a = 0.0;
	vec3 pc = vec3(1.0);
	if (weather == 1 || weather == 2) {
		a = rain(ua, t, weather == 2 ? 0.86 : 0.93, weather == 2 ? 30.0 : 12.0) * (weather == 2 ? 1.0 : 0.8);
		pc = vec3(0.75, 0.82, 0.95);
		tint *= weather == 2 ? 0.7 : 0.85;
	} else if (weather == 3) {
		a = particles(ua, t * 0.1, 26.0, vec2(0.1, -1.0), 0.08) + particles(ua, t * 0.06, 12.0, vec2(-0.1, -1.0), 0.1) * 0.7;
	} else if (weather == 4) {
		a = 0.0;
	} else if (season == 0) {
		a = particles(ua + vec2(sin(t + uv.y * 6.0) * 0.02, 0.0), t * 0.15, 18.0, vec2(-0.4, -1.0), 0.12);
		pc = vec3(1.0, 0.78, 0.85);
	} else if (season == 2) {
		a = particles(ua + vec2(sin(t * 0.7 + uv.y * 4.0) * 0.03, 0.0), t * 0.12, 14.0, vec2(0.3, -1.0), 0.14);
		pc = vec3(0.85, 0.45, 0.15);
	}
	a = clamp(a, 0.0, 1.0);
	float fog = weather == 4 ? 0.35 + 0.25 * noise(ua * 3.0 + vec2(t * 0.05, 0.0)) : 0.0;
	vec3 night_col = vec3(0.05, 0.07, 0.18);
	vec3 col = mix(tint, pc, a);
	col = mix(col, vec3(0.85), fog);
	col = mix(col, night_col, night * 0.85);
	float alpha = max(0.18 * intensity, a * intensity);
	alpha = max(alpha, fog);
	alpha = max(alpha, night * 0.55);
	COLOR = vec4(col, alpha);
}
