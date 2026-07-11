# Golden Prompt: Compact I2V

## Source Brief

Animate a product still without changing the product.

## Internal Prompt Specification

Mode: I2V. Internal binding `product` controls product identity. Current clip action: one light sweep. Endpoint: logo remains readable. The binding is a typed segment; the selected surface profile decides its prompt-visible form.

## Typed Segment Composition

`binding(product)` + ` is the product identity reference; preserve its logo, shape, color, and material exactly. Only a narrow warm light sweep moves across the glass, ending with the label cleanly readable. Camera stays locked. Sound: one soft chime at the final highlight.`

`binding(product)` is typed plan notation, not text to paste. Render it through the selected, current surface profile.

## Lint Result

semantic lint: pass; surface render: required

## Control-Critical Sentences

why this remains: the typed `product` segment plus `is the product identity reference` binds the still to identity only.

why this remains: `Only a narrow warm light sweep moves` prevents static product details from being regenerated.
