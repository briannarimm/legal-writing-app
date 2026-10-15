-- APA 7th reference list: the "References" heading starts a new page, and the entries after it
-- (up to the next top-level heading) get a hanging indent. Used by templates/assignment.
--   PDF:  \clearpage, then the entries inside the apareflist environment (document.latex)
--   Word: a page break, then the entries in the "Bibliography" style (hanging indent)

local function is_refs(b)
  return b.t == 'Header' and b.level == 1
    and pandoc.utils.stringify(b.content):lower():match('^%s*references?%s*$') ~= nil
end

function Pandoc(doc)
  local latex = FORMAT:match('latex') ~= nil
  local docx = FORMAT:match('docx') ~= nil
  if not (latex or docx) then return nil end
  local out, buf, inrefs = pandoc.List{}, pandoc.List{}, false
  local function close()
    if not inrefs then return end
    if #buf > 0 then
      if latex then
        out:insert(pandoc.RawBlock('latex', '\\begin{apareflist}'))
        out:extend(buf)
        out:insert(pandoc.RawBlock('latex', '\\end{apareflist}'))
      else
        out:insert(pandoc.Div(buf, pandoc.Attr('', {}, { ['custom-style'] = 'Bibliography' })))
      end
    end
    buf, inrefs = pandoc.List{}, false
  end
  for _, b in ipairs(doc.blocks) do
    if b.t == 'Header' and b.level == 1 then close() end
    if is_refs(b) then
      if latex then out:insert(pandoc.RawBlock('latex', '\\clearpage'))
      else out:insert(pandoc.RawBlock('openxml', '<w:p><w:r><w:br w:type="page"/></w:r></w:p>')) end
      out:insert(b)
      inrefs = true
    elseif inrefs then buf:insert(b)
    else out:insert(b) end
  end
  close()
  doc.blocks = out
  return doc
end
