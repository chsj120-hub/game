shader_type canvas_item;
// 전통 한지 질감: 닥나무 섬유(길쭉한 노이즈) + 얼룩 + 가장자리 번짐

uniform vec4 paper_color : source_color = vec4(0.91, 0.86, 0.74, 1.0);
uniform vec4 fiber_color : source_color = vec4(0.78, 0.70, 0.55, 1.0);
uniform float fiber_density = 90.0;
uniform float vignette = 0.35;

float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }

float noise(vec2 p) {
	vec2 i = floor(p);
	vec2 f = fract(p);
	vec2 u = f * f * (3.0 - 2.0 * f);
	return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), u.x),
			   mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), u.x), u.y);
}

float fbm(vec2 p) {
	float v = 0.0;
	float a = 0.5;
	for (int i = 0; i < 5; i++) { v += a * noise(p); p *= 2.03; a *= 0.5; }
	return v;
}

void fragment() {
	vec2 uv = UV;
	// 섬유: 한 방향으로 늘린 노이즈 여러 겹
	float fibers = 0.0;
	fibers += smoothstep(0.72, 0.8, noise(vec2(uv.x * fiber_density * 0.15, uv.y * fiber_density)));
	fibers += smoothstep(0.75, 0.82, noise(vec2(uv.y * fiber_density * 0.2 + 13.0, uv.x * fiber_density * 1.3)));
	float blotch = fbm(uv * 6.0) * 0.12;
	vec3 col = mix(paper_color.rgb, fiber_color.rgb, clamp(fibers * 0.5 + blotch, 0.0, 1.0));
	float d = distance(uv, vec2(0.5));
	col *= 1.0 - vignette * smoothstep(0.35, 0.8, d);
	COLOR = vec4(col, 1.0);
}
