-- Annotated bibliography layout (templates/bibliography). app/cites.py turns each entry into
--   Div.bib-entry [ Para (the formatted citation), Div.bib-annotation [ the annotation ] ]
-- PDF:  environments bibentry (hanging indent) and bibannotation (indented block), in document.latex
-- Word: paragraph styles "Bibliography" and "Annotation" (templates/bibliography/reference.docx)

local function latex(name, blocks, wrap)
  local out = { pandoc.RawBlock('latex', '\\begin{' .. name .. '}') }
  for _, b in ipairs(blocks) do out[#out + 1] = b end
  out[#out + 1] = pandoc.RawBlock('latex', '\\end{' .. name .. '}')
  return out
end

local function styled(style, blocks)
  return pandoc.Div(blocks, pandoc.Attr('', {}, { ['custom-style'] = style }))
end

function Div(d)
  local is_latex, is_docx = FORMAT:match('latex') ~= nil, FORMAT:match('docx') ~= nil
  if d.classes:includes('bib-annotation') then
    if is_latex then return latex('bibannotation', d.content) end
    if is_docx then return styled('Annotation', d.content) end
    return nil
  end
  if d.classes:includes('bib-entry') then
    local entry, rest = d.content[1], {}
    for i = 2, #d.content do rest[#rest + 1] = d.content[i] end
    local out
    if is_latex then out = latex('bibentry', { entry })
    elseif is_docx then out = { styled('Bibliography', { entry }) }
    else return nil end
    for _, b in ipairs(rest) do out[#out + 1] = b end
    return out
  end
end
