import { Table, TableCell, TableHeader, TableRow } from '@tiptap/extension-table'
import { tableSpan } from './tableAttributes'

function cellAttributes() {
  return {
    colspan: { default: 1, parseHTML: (element: HTMLElement) => tableSpan(element.getAttribute('colspan')) },
    rowspan: { default: 1, parseHTML: (element: HTMLElement) => tableSpan(element.getAttribute('rowspan')) },
    // Column resizing is deliberately disabled; clipboard dimensions are not persisted.
    colwidth: { default: null, parseHTML: () => null, rendered: false },
  }
}

/** Use the same semantic, bounded table format for editing, paste, and public rendering. */
export const articleTableExtensions = [
  Table.extend({
    renderHTML() { return ['table', {}, ['tbody', 0]] },
  }).configure({ resizable: false, allowTableNodeSelection: true }),
  TableRow,
  TableCell.extend({ addAttributes: cellAttributes }),
  TableHeader.extend({ addAttributes: cellAttributes }),
]
