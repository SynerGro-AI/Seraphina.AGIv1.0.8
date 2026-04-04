# dashboard_updates_v8.7.py
# Code Audit Tab Update + Kabbalistic Visualizer Tab for Glyph Language Engine v8.7

# Replace your current Code Audit tab with this refined version:

with gr.TabItem("🔍 Code Audit (Glyph v8.7 + 16D Resonance)"):
    gr.Markdown("### 🌌 Glyph Language Engine v8.7 — 16D Binary/Float + Live Resonance Gauge")

    with gr.Row():
        with gr.Column(scale=1):
            audit_input = gr.Textbox(label="Code / Token / Component", lines=12, placeholder="Paste code or token...")
            dim_slider = gr.Slider(4, 16, value=16, step=4, label="Dimension (4D fast → 16D quantum)")
            anchor_checkbox = gr.Checkbox(label="Enable Justice & Mercy Anchor (Truth & Humility)", value=False)
            analyze_btn = gr.Button("🔍 Analyze with Glyph Engine", variant="primary")

    with gr.Row():
        glyph_output = gr.JSON(label="Full Glyph Result")
        resonance_gauge = gr.Plot(label="16D Resonance Gauge (0.0 – 1.0)")
        visual_preview = gr.Markdown(label="🌟 Visual Glyph + Kabbalistic Note")

def analyze_code(code, dimension, enable_anchor):
        anchor_flag = "--applyAnchor true" if enable_anchor else "--applyAnchor false"
        result = call_glyph_cipher(f"--op gematriaBinaryFloat --text {shlex.quote(code)} --dimension {dimension} {anchor_flag}")

        # Holographic resonance gauge
        gauge_fig = go.Figure(go.Indicator(
            mode="gauge+number+delta",
            value=float(result.get('resonance', 0.5)),
            title={"text": f"16D Resonance ({result.get('tier', 'deep')})"},
            gauge={
                "axis": {"range": [0, 1]},
                "bar": {"color": "#00ffcc" if float(result.get('resonance', 0)) > 0.7 else "#ffaa00"},
                "steps": [{"range": [0, 0.5], "color": "rgba(255,100,100,0.3)"},
                          {"range": [0.5, 0.8], "color": "rgba(255,200,100,0.3)"},
                          {"range": [0.8, 1], "color": "rgba(0,255,150,0.4)"}]
            }
        ))
        gauge_fig.update_layout(height=320, paper_bgcolor="rgba(0,0,0,0.8)")

        # Justice & Mercy Anchor status
        anchor_status = ""
        if result.get('anchorActivated', False):
            anchor_status = f"""
**Justice & Mercy Anchor**: ✅ Activated (+{result.get('anchorBias', '0.000')})
**Anchor Note**: {result.get('anchorNote', 'Truth and Humility reign')}
**Safety**: {result.get('safetyNote', 'Anchor applied safely')}
---
"""

        visual = f"""{anchor_status}**Glyph**: {result.get('finalGlyph', 'N/A')}
**Resonance**: {result.get('resonance', 'N/A')} ({'Anchored' if result.get('anchorActivated') else 'Raw'})
**Raw Resonance**: {result.get('rawResonance', 'N/A')}
**Kabbalistic Note**: {result.get('kabbalisticNote', 'Geometric resonance')}
        """

        return result, gauge_fig, visual

    analyze_btn.click(
        analyze_code,
        inputs=[audit_input, dim_slider, anchor_checkbox],
        outputs=[glyph_output, resonance_gauge, visual_preview]
    )

# Add this as a NEW tab for mystical exploration:

with gr.TabItem("🌟 Kabbalistic Glyph Visualizer"):
    gr.Markdown("### Kabbalistic Glyph Visualizer — Gematria + Cosmic Meaning + Justice & Mercy Anchor")
    viz_input = gr.Textbox(label="Token / Code / Concept", value="truth and humility")
    viz_anchor = gr.Checkbox(label="Apply Justice & Mercy Anchor", value=True)
    viz_btn = gr.Button("Visualize Kabbalistic Glyph")
    viz_output = gr.Markdown()

    def kabbalistic_visualize(token, enable_anchor):
        anchor_flag = "--applyAnchor true" if enable_anchor else "--applyAnchor false"
        result = call_glyph_cipher(f"--op gematriaBinaryFloat --text {shlex.quote(token)} --dimension 8 {anchor_flag}")

        anchor_info = ""
        if result.get('anchorActivated', False):
            anchor_info = f"""
**Justice & Mercy Anchor**: ✅ Applied (+{result.get('anchorBias', '0.000')})
**Anchor Status**: {result.get('justiceMercyAnchor', 'Neutral')}
**Safety Note**: {result.get('safetyNote', 'Truth and Humility reign')}
---
"""

        return f"""{anchor_info}**Token**: {token}
**Gematria Seed**: {result.get('gematriaSeed')}
**Final Glyph**: {result.get('finalGlyph')}
**Resonance**: {result.get('resonance')} ({'Anchored' if result.get('anchorActivated') else 'Raw'})
**Raw Resonance**: {result.get('rawResonance', 'N/A')}
**Kabbalistic Meaning**: {result.get('kabbalisticNote')}
**Anchor Note**: {result.get('anchorNote', 'Core geometric resonance only')}
**Roman Wheel Chain**: {result.get('floatChain')[:5]}... (showing first 5 values)
        """

    viz_btn.click(kabbalistic_visualize, inputs=[viz_input, viz_anchor], outputs=[viz_output])

# Required imports for the dashboard:
import plotly.graph_objects as go
import shlex