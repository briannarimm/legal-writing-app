-- Word-output front and back matter for memos and briefs (the PDF templates do this in LaTeX).
--   doctype: memo   -> MEMORANDUM header with To / From / Date / Re
--   doctype: apa    -> APA 7th student title page, then the title again above the paper
--   doctype: brief  -> cover page, table of contents, signature block, certificates
-- Set from each template's docx.yaml. Word fills in the table of contents when the file is
-- opened (choose "Update field" if Word asks). A table of authorities is not generated for
-- Word; use the PDF for that.

local function s(v) if v == nil then return "" end if type(v) == "string" then return v end return pandoc.utils.stringify(v) end
local function list(v)
  if not v then return {} end
  if pandoc.utils.type(v) == 'List' then
    local out = {}
    for _, x in ipairs(v) do out[#out + 1] = s(x) end
    return out
  end
  return { s(v) }
end

local function centered(text, bold)
  local inl = pandoc.Inlines{ pandoc.Str(text) }
  if bold then inl = pandoc.Inlines{ pandoc.Strong(inl) } end
  return pandoc.Div({ pandoc.Para(inl) }, pandoc.Attr('', {}, { ['custom-style'] = 'Centered' }))
end
local function plain(text, bold)
  local inl = pandoc.Inlines(text)
  if bold then inl = pandoc.Inlines{ pandoc.Strong(inl) } end
  return pandoc.Div({ pandoc.Para(inl) }, pandoc.Attr('', {}, { ['custom-style'] = 'Compact' }))
end
local pagebreak = pandoc.RawBlock('openxml', '<w:p><w:r><w:br w:type="page"/></w:r></w:p>')
local function field(instr, placeholder)
  return pandoc.RawBlock('openxml',
    '<w:p><w:r><w:fldChar w:fldCharType="begin" w:dirty="true"/></w:r><w:r><w:instrText xml:space="preserve"> '
    .. instr .. ' </w:instrText></w:r><w:r><w:fldChar w:fldCharType="separate"/></w:r><w:r><w:t>'
    .. placeholder .. '</w:t></w:r><w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>')
end
local function heading(text)
  return pandoc.Div({ pandoc.Header(1, pandoc.Inlines(text), pandoc.Attr('', { 'unnumbered' })) })
end

local function memo(doc)
  local m = doc.meta
  local out = pandoc.List{ centered('MEMORANDUM', true) }
  if m.privileged then out:insert(centered(s(m.privileged), true)) end
  local function row(label, v)
    if v then out:insert(pandoc.Div({ pandoc.Para({ pandoc.Strong(pandoc.Inlines(label)), pandoc.Space(),
      table.unpack(pandoc.Inlines(s(v))) }) }, pandoc.Attr('', {}, { ['custom-style'] = 'Compact' }))) end
  end
  row('TO:', m.to); row('FROM:', m.from); row('CC:', m.cc)
  row('DATE:', m.date or os.date('%B %e, %Y')); row('RE:', m.re)
  out:insert(pandoc.HorizontalRule())
  out:extend(doc.blocks)
  doc.blocks = out
  doc.meta.title = nil; doc.meta.author = nil; doc.meta.date = nil
  return doc
end

local function apa(doc)
  local m = doc.meta
  local title = m.title and s(m.title) or ''
  local out = pandoc.List{}
  for _ = 1, 3 do out:insert(centered('')) end
  if title ~= '' then out:insert(centered(title, true)) end
  out:insert(centered(''))
  for _, a in ipairs(list(m.author)) do out:insert(centered(a)) end
  for _, key in ipairs({ 'affiliation', 'course', 'instructor' }) do
    if m[key] then out:insert(centered(s(m[key]))) end
  end
  out:insert(centered(m.date and s(m.date) or os.date('%B %e, %Y')))
  out:insert(pagebreak)
  if title ~= '' then out:insert(centered(title, true)) end
  out:extend(doc.blocks)
  doc.blocks = out
  doc.meta.title = nil; doc.meta.author = nil; doc.meta.date = nil
  return doc
end

local function brief(doc)
  local m = doc.meta
  local out = pandoc.List{}
  if m['case-number'] then out:insert(centered(s(m['case-number']), true)) end
  for _, c in ipairs(list(m.court)) do out:insert(centered(c, true)) end
  if m.appellant then
    out:insert(plain(s(m.appellant.name))); out:insert(plain('      ' .. s(m.appellant.role)))
    out:insert(plain('v.'))
    out:insert(plain(s(m.appellee.name))); out:insert(plain('      ' .. s(m.appellee.role)))
  end
  for _, c in ipairs(list(m['appeal-from'])) do out:insert(centered(c)) end
  out:insert(centered(s(m['brief-title'] or 'BRIEF'), true))
  for _, c in ipairs(list(m.counsel)) do out:insert(plain(c)) end
  out:insert(pagebreak)
  out:insert(heading('Table of Contents'))
  out:insert(field('TOC \\o "1-4" \\h \\z \\u', 'Right-click here and choose Update Field to build the table of contents.'))
  out:insert(pagebreak)
  out:extend(doc.blocks)

  out:insert(plain('Respectfully submitted,'))
  if m.signature then out:insert(plain('/s/ ' .. s(m.signature))) end
  for _, c in ipairs(list(m.counsel)) do out:insert(plain(c)) end
  out:insert(pagebreak)

  local date = m.date and s(m.date) or '[date]'
  local words = '[number of words: use Word\'s Review > Word Count]'
  if s(m.jurisdiction) == 'missouri' then
    out:insert(heading('Certificate of Compliance and Service'))
    out:insert(pandoc.Para(pandoc.Inlines('Pursuant to Rule 84.06(c), the undersigned certifies that: (1) this brief includes the information required by Rule 55.03; (2) this brief complies with the limitations contained in Rule 84.06(b); and (3) this brief contains ' .. words .. '.')))
    out:insert(pandoc.Para(pandoc.Inlines('On ' .. date .. ', ' .. (m.service and s(m.service) or 'a copy of this brief was served through the Missouri Courts electronic filing system on all counsel of record.'))))
  else
    out:insert(heading('Certificate of Compliance'))
    out:insert(pandoc.Para(pandoc.Inlines('1. This brief complies with the type-volume limitation of Fed. R. App. P. 32(a)(7)(B) because it contains ' .. words .. ', excluding the parts of the brief exempted by Fed. R. App. P. 32(f).')))
    out:insert(pandoc.Para(pandoc.Inlines('2. This brief complies with the typeface requirements of Fed. R. App. P. 32(a)(5) and the type-style requirements of Fed. R. App. P. 32(a)(6) because it has been prepared in a proportionally spaced typeface in 14-point Times New Roman.')))
    out:insert(pandoc.Para(pandoc.Inlines('3. Pursuant to 8th Cir. R. 28A(h), the electronic version of this brief was scanned for viruses and is virus-free.')))
    if m.signature then out:insert(plain('/s/ ' .. s(m.signature))) end
    out:insert(pagebreak)
    out:insert(heading('Certificate of Service'))
    out:insert(pandoc.Para(pandoc.Inlines('I certify that on ' .. date .. ', I electronically filed the foregoing brief with the Clerk of ' .. (m['court-name'] and s(m['court-name']) or 'the Court') .. ' by using the CM/ECF system. Participants in the case who are registered CM/ECF users will be served by the CM/ECF system.')))
  end
  if m.signature then out:insert(plain('/s/ ' .. s(m.signature))) end
  doc.blocks = out
  doc.meta.title = nil; doc.meta.author = nil; doc.meta.date = nil
  return doc
end

function Pandoc(doc)
  local kind = doc.meta.doctype and s(doc.meta.doctype)
  if kind == 'memo' then return memo(doc) end
  if kind == 'brief' then return brief(doc) end
  if kind == 'apa' then return apa(doc) end
end
