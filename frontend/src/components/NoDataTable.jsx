const DEFAULT_COLUMNS = [
  'Requirement',
  'Lead',
  'Recruiter',
  'Priority',
  'Submissions',
  'Status',
]

export default function NoDataTable({
  title = 'No Data',
  columns = DEFAULT_COLUMNS,
  rowCount = 5,
}) {
  const emptyRows = Array.from({
    length: rowCount,
  })
  const getPlaceholder = (column) => {
    const normalized = column.toLowerCase()
    const zeroColumns = [
      'submissions',
      'no. of submissions',
      'requirements',
      'submitted',
      'fbk pending',
      'interviews',
      'closures',
    ]

    return zeroColumns.includes(normalized) ? '0' : '-'
  }

  return (
    <div className="animate-[fadeSlide_0.8s_ease] overflow-hidden rounded-[30px] border border-cyan-500/10 bg-[#06101f]/95 backdrop-blur-xl shadow-[0_0_60px_rgba(0,255,255,0.05)]">
      <div className="border-b border-[rgba(0,245,255,0.08)] px-6 py-6">
        <h2 className="text-4xl font-black text-white">
          {title}
        </h2>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[900px]">
          <thead className="bg-[#0b1628]">
            <tr className="border-b border-white/[0.05]">
              {columns.map((column) => (
                <th
                  key={column}
                  className="px-8 py-5 text-left text-sm font-black uppercase tracking-[0.28em] text-cyan-300"
                >
                  {column}
                </th>
              ))}
            </tr>
          </thead>

          <tbody>
            {emptyRows.map((_, rowIndex) => (
              <tr
                key={rowIndex}
                className="border-b border-white/[0.03]"
              >
                {columns.map((column) => (
                  <td
                    key={column}
                    className="px-8 py-6 text-slate-500"
                  >
                    {getPlaceholder(column)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
