# GitInstaller — WebUI Design Specification

> Drop-in replaceable design file. All AI-generated Gradio WebUIs will follow this spec.
> Replace this file to change the theme for all future generated WebUIs.

## Branding

- **App Name:** GitInstaller
- **Footer Text:** Built with GitInstaller • github.com/arjun-arihant/gitinstaller
- **Powered By:** Gradio

## Color Palette

| Token           | Value     | Usage                      |
|-----------------|-----------|----------------------------|
| primary         | #4A90D9   | Buttons, links, accents    |
| primary_hover   | #5DA0E9   | Hover states               |
| secondary       | #2c2d33   | Cards, elevated surfaces   |
| background      | #1a1b1e   | Page background            |
| surface         | #25262b   | Input backgrounds          |
| text_primary    | #e1e2e6   | Headings, body text        |
| text_secondary  | #909296   | Labels, placeholders       |
| text_muted      | #6b6d72   | Disabled, hints            |
| success         | #51cf66   | Success states, checkmarks |
| error           | #f87171   | Error states, warnings     |
| border          | #3a3b41   | Borders, dividers          |

## Typography

- **Font Family:** -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif
- **Monospace:** "Cascadia Code", "Consolas", "Fira Code", monospace
- **Heading Size:** 24px (h1), 18px (h2), 15px (h3)
- **Body Size:** 14px
- **Label Size:** 13px
- **Font Weight:** 400 normal, 600 semibold, 700 bold

## Spacing & Layout

- **Border Radius:** 8px (components), 12px (cards/containers)
- **Padding:** 12px-16px (inputs), 14px-18px (cards)
- **Gap:** 8px (compact), 12px (normal), 16px (sections)
- **Max Width:** 900px (main container)

## Component Guidelines

### Buttons
- Primary: solid background with `primary` color, white text, 8px radius
- Secondary: transparent with border, text_primary color
- Hover: glow effect with 3px box-shadow using primary at 25% opacity

### Inputs
- Background: `surface` color
- Border: 1px solid `border`
- Focus: border changes to `primary`, 3px glow
- Placeholder: `text_muted`

### Cards / Blocks
- Background: `secondary`
- Border: 1px solid `border`
- Border-radius: 12px
- Shadow: subtle 2px 8px rgba(0,0,0,0.3)

### Terminal / Code Output
- Background: #111113
- Font: monospace, 12px
- Color: #d4d4d4

## Gradio Theme Implementation

The generated WebUI must use `gr.themes.Base()` subclass with:
```python
theme = gr.themes.Base(
    primary_hue=gr.themes.Color(
        c50="#e8f0fe", c100="#d0e1fc", c200="#a1c3f9",
        c300="#72a5f6", c400="#4A90D9", c500="#4A90D9",
        c600="#3b7ac4", c700="#2c64af", c800="#1d4e9a",
        c900="#0e3885", c950="#072260"
    ),
    neutral_hue=gr.themes.Color(
        c50="#e1e2e6", c100="#c3c5cc", c200="#909296",
        c300="#6b6d72", c400="#55565c", c500="#44454b",
        c600="#3a3b41", c700="#2c2d33", c800="#25262b",
        c900="#1a1b1e", c950="#111113"
    ),
    font=["-apple-system", "BlinkMacSystemFont", "Segoe UI", "Roboto", "sans-serif"],
    font_mono=["Cascadia Code", "Consolas", "Fira Code", "monospace"],
).set(
    body_background_fill="#1a1b1e",
    body_background_fill_dark="#1a1b1e",
    block_background_fill="#25262b",
    block_background_fill_dark="#25262b",
    block_border_color="#3a3b41",
    block_border_color_dark="#3a3b41",
    block_label_text_color="#909296",
    block_label_text_color_dark="#909296",
    block_title_text_color="#e1e2e6",
    block_title_text_color_dark="#e1e2e6",
    input_background_fill="#2c2d33",
    input_background_fill_dark="#2c2d33",
    input_border_color="#3a3b41",
    input_border_color_dark="#3a3b41",
    button_primary_background_fill="#4A90D9",
    button_primary_background_fill_dark="#4A90D9",
    button_primary_text_color="#ffffff",
    button_primary_text_color_dark="#ffffff",
    border_color_primary="#3a3b41",
    border_color_primary_dark="#3a3b41",
)
```

## Footer

Every generated WebUI MUST include a footer:
```python
gr.Markdown(
    "<center style='color: #6b6d72; font-size: 12px; margin-top: 16px;'>"
    "Built with <a href='https://github.com/arjun-arihant/gitinstaller' "
    "style='color: #4A90D9; text-decoration: none;'>GitInstaller</a>"
    "</center>"
)
```
