/** Split bar: sources on the companies' own websites vs news, analysts and databases. */
export function SourceMix({ company, other }: { company: number; other: number }) {
  return (
    <div>
      <div
        role="img"
        aria-label={`${company} sources from companies' own websites, ${other} from news, analysts and databases`}
        className="flex h-[18px] gap-[3px] overflow-hidden rounded-full"
      >
        {company > 0 && <span className="bg-accent" style={{ flex: company }} />}
        {other > 0 && <span className="bg-bar" style={{ flex: other }} />}
      </div>
      <ul className="mt-5 space-y-3 text-[15px]">
        <li className="flex items-center gap-2.5">
          <span aria-hidden="true" className="h-2.5 w-2.5 rounded-[3px] bg-accent" />
          Companies’ own websites
          <b className="ml-auto tabular-nums">{company}</b>
        </li>
        <li className="flex items-center gap-2.5">
          <span aria-hidden="true" className="h-2.5 w-2.5 rounded-[3px] bg-bar" />
          News, analysts and databases
          <b className="ml-auto tabular-nums">{other}</b>
        </li>
      </ul>
    </div>
  );
}
