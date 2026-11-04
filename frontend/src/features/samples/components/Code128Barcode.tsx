// Code 128 pattern table (patterns for values 0-106)
// Each number corresponds to bar/space module widths
const CODE128_PATTERNS: string[] = [
  "212222", "222122", "222221", "121223", "121322", "131222", "122213", "122312", "132212", "221213", // 0-9
  "221312", "231212", "112232", "122132", "122231", "113222", "123122", "123221", "223211", "221132", // 10-19
  "221231", "213212", "223112", "312131", "311222", "321122", "321221", "312212", "322112", "322211", // 20-29
  "212123", "212321", "232121", "111323", "131123", "131321", "112313", "132113", "132311", "211313", // 30-39
  "231113", "231311", "112133", "112331", "132131", "113123", "113321", "133121", "313121", "211331", // 40-49
  "231131", "213113", "213311", "213131", "311123", "311321", "331121", "312113", "312311", "332111", // 50-59
  "314111", "221411", "431111", "111224", "111422", "121124", "121421", "141122", "141221", "112214", // 60-69
  "112412", "122114", "122411", "142112", "142211", "241211", "221114", "413111", "241112", "134111", // 70-79
  "111242", "121142", "121241", "114212", "124112", "124211", "411212", "421112", "421211", "212141", // 80-89
  "214121", "412121", "111143", "111341", "131141", "114113", "114311", "411113", "411311", "113141", // 90-99
  "114131", "311141", "411131", "211412", "211214", "211232", "2331112", // 100-106 (106 is STOP)
];

const START_B = 104;
const STOP = 106;

function encodeCode128B(text: string): string[] {
  const codes: number[] = [START_B];
  let checkSum = START_B;
  let weight = 1;

  for (let i = 0; i < text.length; i++) {
    const charCode = text.charCodeAt(i);
    const code = charCode - 32;
    if (code >= 0 && code <= 95) {
      codes.push(code);
      checkSum += code * weight;
      weight += 1;
    }
  }

  const checkDigit = checkSum % 103;
  codes.push(checkDigit);
  codes.push(STOP);

  return codes.map((c) => CODE128_PATTERNS[c] || CODE128_PATTERNS[0]!);
}

interface Code128BarcodeProps {
  value: string;
  height?: number;
  barWidth?: number;
  showText?: boolean;
  className?: string;
}

export function Code128Barcode({
  value,
  height = 50,
  barWidth = 2,
  showText = false,
  className = "",
}: Code128BarcodeProps): JSX.Element {
  const patterns = encodeCode128B(value);

  // Convert width strings (e.g. "212222") to array of rectangles
  const rects: Array<{ x: number; width: number }> = [];
  let currentX = 10; // Left quiet zone

  patterns.forEach((pattern) => {
    let isBar = true;
    for (let i = 0; i < pattern.length; i++) {
      const w = parseInt(pattern[i]!, 10) * barWidth;
      if (isBar) {
        rects.push({ x: currentX, width: w });
      }
      currentX += w;
      isBar = !isBar;
    }
  });

  const totalWidth = currentX + 10; // Right quiet zone

  return (
    <div className={`inline-flex flex-col items-center select-none ${className}`}>
      <svg
        width={totalWidth}
        height={height}
        viewBox={`0 0 ${totalWidth} ${height}`}
        className="shape-crispEdges"
        style={{ shapeRendering: "crispEdges" }}
        role="img"
        aria-label={`Barcode for ${value}`}
      >
        <rect width={totalWidth} height={height} fill="#ffffff" />
        {rects.map((r, idx) => (
          <rect
            key={idx}
            x={r.x}
            y={0}
            width={r.width}
            height={height}
            fill="#000000"
          />
        ))}
      </svg>
      {showText && (
        <span className="font-mono text-xs font-semibold tracking-wider text-slate-800 mt-1">
          {value}
        </span>
      )}
    </div>
  );
}
