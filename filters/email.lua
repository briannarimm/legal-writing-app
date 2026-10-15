-- Email output: mail programs drop CSS classes, so small caps and similar
-- must be written as inline styles. Authority marks (briefs only) are unwrapped.
function SmallCaps(el)
  return pandoc.Span(el.content, pandoc.Attr('', {}, { style = 'font-variant: small-caps' }))
end
function Span(el)
  if el.classes:includes('auth') then return el.content end
end
