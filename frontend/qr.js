const QR_TOTAL_CODEWORDS = [26, 44, 70, 100, 134, 172, 196, 242, 292, 346];
const QR_EC_CODEWORDS_PER_BLOCK = [10, 16, 26, 18, 24, 16, 18, 22, 22, 26];
const QR_BLOCK_GROUPS = [[1, 0], [1, 0], [1, 0], [2, 0], [2, 0], [4, 0], [4, 0], [2, 2], [3, 2], [4, 1]];
const QR_ALIGNMENT_CENTERS = [
  [], [6, 18], [6, 22], [6, 26], [6, 30], [6, 34],
  [6, 22, 38], [6, 24, 42], [6, 26, 46], [6, 28, 50],
];
const QR_VERSION_BITS = [0, 0, 0, 0, 0, 0, 0x07c94, 0x085bc, 0x09a99, 0x0a4d3];
const QR_FORMAT_BITS = [0x5412, 0x5125, 0x5e7c, 0x5b4b, 0x45f9, 0x40ce, 0x4f97, 0x4aa0];
const QR_MAX_VERSION = QR_TOTAL_CODEWORDS.length;
const QR_MODE_BYTE = 4;
const QR_PAD_CODEWORDS = [0xec, 0x11];
const QR_QUIET_ZONE = 4;
const QR_GF_PRIMITIVE = 0x11d;

const QR_EXPONENTS = new Uint8Array(512);
const QR_LOGARITHMS = new Uint8Array(256);

function qrBuildFieldTables() {
  let value = 1;
  for (let power = 0; power < 255; power += 1) {
    QR_EXPONENTS[power] = value;
    QR_LOGARITHMS[value] = power;
    value <<= 1;
    if (value & 0x100) value ^= QR_GF_PRIMITIVE;
  }
  for (let power = 255; power < 512; power += 1) QR_EXPONENTS[power] = QR_EXPONENTS[power - 255];
}

qrBuildFieldTables();

function qrMultiply(left, right) {
  if (!left || !right) return 0;
  return QR_EXPONENTS[QR_LOGARITHMS[left] + QR_LOGARITHMS[right]];
}

function qrGeneratorPolynomial(degree) {
  let polynomial = [1];
  for (let step = 0; step < degree; step += 1) {
    const next = new Array(polynomial.length + 1).fill(0);
    for (let index = 0; index < polynomial.length; index += 1) {
      next[index] ^= polynomial[index];
      next[index + 1] ^= qrMultiply(polynomial[index], QR_EXPONENTS[step]);
    }
    polynomial = next;
  }
  return polynomial;
}

function qrErrorCorrection(dataCodewords, count) {
  const generator = qrGeneratorPolynomial(count);
  const buffer = dataCodewords.concat(new Array(count).fill(0));
  for (let index = 0; index < dataCodewords.length; index += 1) {
    const factor = buffer[index];
    if (!factor) continue;
    for (let step = 0; step < generator.length; step += 1) {
      buffer[index + step] ^= qrMultiply(generator[step], factor);
    }
  }
  return buffer.slice(dataCodewords.length);
}

function qrDataCapacity(version) {
  const index = version - 1;
  const groups = QR_BLOCK_GROUPS[index];
  return QR_TOTAL_CODEWORDS[index] - QR_EC_CODEWORDS_PER_BLOCK[index] * (groups[0] + groups[1]);
}

function qrCountBits(version) {
  return version < 10 ? 8 : 16;
}

function qrPickVersion(byteLength) {
  for (let version = 1; version <= QR_MAX_VERSION; version += 1) {
    const needed = 4 + qrCountBits(version) + byteLength * 8;
    if (needed <= qrDataCapacity(version) * 8) return version;
  }
  return 0;
}

function qrTextBytes(text) {
  if (typeof TextEncoder === "function") return Array.from(new TextEncoder().encode(String(text)));
  const escaped = encodeURIComponent(String(text));
  const bytes = [];
  for (let index = 0; index < escaped.length; index += 1) {
    if (escaped.charAt(index) === "%") {
      bytes.push(parseInt(escaped.slice(index + 1, index + 3), 16));
      index += 2;
    } else {
      bytes.push(escaped.charCodeAt(index));
    }
  }
  return bytes;
}

function qrDataCodewords(bytes, version) {
  const capacity = qrDataCapacity(version);
  const bits = [];
  const push = (value, length) => {
    for (let position = length - 1; position >= 0; position -= 1) bits.push((value >> position) & 1);
  };
  push(QR_MODE_BYTE, 4);
  push(bytes.length, qrCountBits(version));
  for (const byte of bytes) push(byte, 8);
  const limit = capacity * 8;
  for (let step = 0; step < 4 && bits.length < limit; step += 1) bits.push(0);
  while (bits.length % 8) bits.push(0);
  const codewords = [];
  for (let index = 0; index < bits.length; index += 8) {
    let value = 0;
    for (let offset = 0; offset < 8; offset += 1) value = (value << 1) | bits[index + offset];
    codewords.push(value);
  }
  let padIndex = 0;
  while (codewords.length < capacity) {
    codewords.push(QR_PAD_CODEWORDS[padIndex % QR_PAD_CODEWORDS.length]);
    padIndex += 1;
  }
  return codewords;
}

function qrInterleave(codewords, version) {
  const index = version - 1;
  const ecCount = QR_EC_CODEWORDS_PER_BLOCK[index];
  const groups = QR_BLOCK_GROUPS[index];
  const blockCount = groups[0] + groups[1];
  const shortLength = Math.floor(codewords.length / blockCount);
  const blocks = [];
  let offset = 0;
  for (let block = 0; block < blockCount; block += 1) {
    const length = block < groups[0] ? shortLength : shortLength + 1;
    blocks.push(codewords.slice(offset, offset + length));
    offset += length;
  }
  const parity = blocks.map((block) => qrErrorCorrection(block, ecCount));
  const stream = [];
  const longest = shortLength + (groups[1] ? 1 : 0);
  for (let position = 0; position < longest; position += 1) {
    for (const block of blocks) if (position < block.length) stream.push(block[position]);
  }
  for (let position = 0; position < ecCount; position += 1) {
    for (const block of parity) stream.push(block[position]);
  }
  return stream;
}

function qrSideLength(version) {
  return version * 4 + 17;
}

function qrEmptyGrid(size) {
  const grid = [];
  for (let row = 0; row < size; row += 1) grid.push(new Int8Array(size).fill(-1));
  return grid;
}

function qrPlaceFinder(grid, top, left) {
  const size = grid.length;
  for (let row = -1; row <= 7; row += 1) {
    for (let column = -1; column <= 7; column += 1) {
      const y = top + row;
      const x = left + column;
      if (y < 0 || x < 0 || y >= size || x >= size) continue;
      const inside = row >= 0 && row <= 6 && column >= 0 && column <= 6;
      const ring = row === 0 || row === 6 || column === 0 || column === 6;
      const core = row >= 2 && row <= 4 && column >= 2 && column <= 4;
      grid[y][x] = inside && (ring || core) ? 1 : 0;
    }
  }
}

function qrPlaceTiming(grid) {
  const size = grid.length;
  for (let position = 8; position < size - 8; position += 1) {
    const value = position % 2 === 0 ? 1 : 0;
    grid[6][position] = value;
    grid[position][6] = value;
  }
}

function qrPlaceAlignment(grid, version) {
  const size = grid.length;
  const centers = QR_ALIGNMENT_CENTERS[version - 1];
  for (const row of centers) {
    for (const column of centers) {
      if (row === 6 && column === 6) continue;
      if (row === 6 && column === size - 7) continue;
      if (row === size - 7 && column === 6) continue;
      for (let y = -2; y <= 2; y += 1) {
        for (let x = -2; x <= 2; x += 1) {
          const ring = Math.max(Math.abs(y), Math.abs(x));
          grid[row + y][column + x] = ring === 1 ? 0 : 1;
        }
      }
    }
  }
}

function qrReserveFormatAreas(grid) {
  const size = grid.length;
  for (let index = 0; index < 15; index += 1) {
    if (index < 6) grid[index][8] = 0;
    else if (index < 8) grid[index + 1][8] = 0;
    else grid[size - 15 + index][8] = 0;
    if (index < 8) grid[8][size - index - 1] = 0;
    else if (index < 9) grid[8][15 - index] = 0;
    else grid[8][14 - index] = 0;
  }
  grid[size - 8][8] = 1;
}

function qrPlaceVersionInfo(grid, version) {
  if (version < 7) return;
  const size = grid.length;
  const bits = QR_VERSION_BITS[version - 1];
  for (let index = 0; index < 18; index += 1) {
    const value = (bits >> index) & 1;
    grid[Math.floor(index / 3)][size - 11 + (index % 3)] = value;
    grid[size - 11 + (index % 3)][Math.floor(index / 3)] = value;
  }
}

function qrTemplate(version) {
  const size = qrSideLength(version);
  const grid = qrEmptyGrid(size);
  qrPlaceFinder(grid, 0, 0);
  qrPlaceFinder(grid, 0, size - 7);
  qrPlaceFinder(grid, size - 7, 0);
  qrPlaceAlignment(grid, version);
  qrPlaceTiming(grid);
  qrReserveFormatAreas(grid);
  qrPlaceVersionInfo(grid, version);
  return grid;
}

function qrMaskValue(mask, row, column) {
  if (mask === 0) return (row + column) % 2 === 0;
  if (mask === 1) return row % 2 === 0;
  if (mask === 2) return column % 3 === 0;
  if (mask === 3) return (row + column) % 3 === 0;
  if (mask === 4) return (Math.floor(row / 2) + Math.floor(column / 3)) % 2 === 0;
  if (mask === 5) return ((row * column) % 2) + ((row * column) % 3) === 0;
  if (mask === 6) return (((row * column) % 2) + ((row * column) % 3)) % 2 === 0;
  return (((row + column) % 2) + ((row * column) % 3)) % 2 === 0;
}

function qrCloneGrid(grid) {
  return grid.map((row) => Int8Array.from(row));
}

function qrPlaceData(grid, stream, mask) {
  const size = grid.length;
  let direction = -1;
  let row = size - 1;
  let bitIndex = 7;
  let byteIndex = 0;
  for (let column = size - 1; column > 0; column -= 2) {
    const left = column <= 6 ? column - 1 : column;
    const pair = [left, left - 1];
    for (;;) {
      for (const target of pair) {
        if (grid[row][target] !== -1) continue;
        let dark = 0;
        if (byteIndex < stream.length) dark = (stream[byteIndex] >> bitIndex) & 1;
        if (qrMaskValue(mask, row, target)) dark ^= 1;
        grid[row][target] = dark;
        bitIndex -= 1;
        if (bitIndex === -1) {
          byteIndex += 1;
          bitIndex = 7;
        }
      }
      row += direction;
      if (row < 0 || row >= size) {
        row -= direction;
        direction = -direction;
        break;
      }
    }
  }
}

function qrPlaceFormatInfo(grid, mask) {
  const size = grid.length;
  const bits = QR_FORMAT_BITS[mask];
  for (let index = 0; index < 15; index += 1) {
    const value = (bits >> index) & 1;
    if (index < 6) grid[index][8] = value;
    else if (index < 8) grid[index + 1][8] = value;
    else grid[size - 15 + index][8] = value;
    if (index < 8) grid[8][size - index - 1] = value;
    else if (index < 9) grid[8][15 - index] = value;
    else grid[8][14 - index] = value;
  }
  grid[size - 8][8] = 1;
}

function qrRunPenalty(line) {
  let penalty = 0;
  let run = 1;
  for (let index = 1; index < line.length; index += 1) {
    if (line[index] === line[index - 1]) {
      run += 1;
      continue;
    }
    if (run >= 5) penalty += 3 + (run - 5);
    run = 1;
  }
  if (run >= 5) penalty += 3 + (run - 5);
  return penalty;
}

function qrFinderPenalty(line) {
  const pattern = [1, 0, 1, 1, 1, 0, 1];
  let penalty = 0;
  for (let start = 0; start + 7 <= line.length; start += 1) {
    let matches = true;
    for (let offset = 0; offset < 7; offset += 1) {
      if (line[start + offset] !== pattern[offset]) {
        matches = false;
        break;
      }
    }
    if (!matches) continue;
    let before = true;
    for (let offset = 1; offset <= 4; offset += 1) {
      const position = start - offset;
      if (position >= 0 && line[position] !== 0) before = false;
    }
    let after = true;
    for (let offset = 0; offset < 4; offset += 1) {
      const position = start + 7 + offset;
      if (position < line.length && line[position] !== 0) after = false;
    }
    if (before || after) penalty += 40;
  }
  return penalty;
}

function qrPenalty(grid) {
  const size = grid.length;
  let penalty = 0;
  for (let row = 0; row < size; row += 1) {
    const horizontal = [];
    const vertical = [];
    for (let column = 0; column < size; column += 1) {
      horizontal.push(grid[row][column]);
      vertical.push(grid[column][row]);
    }
    penalty += qrRunPenalty(horizontal) + qrRunPenalty(vertical);
    penalty += qrFinderPenalty(horizontal) + qrFinderPenalty(vertical);
  }
  let dark = 0;
  for (let row = 0; row < size - 1; row += 1) {
    for (let column = 0; column < size - 1; column += 1) {
      const value = grid[row][column];
      if (
        value === grid[row][column + 1] &&
        value === grid[row + 1][column] &&
        value === grid[row + 1][column + 1]
      ) {
        penalty += 3;
      }
    }
  }
  for (let row = 0; row < size; row += 1) {
    for (let column = 0; column < size; column += 1) if (grid[row][column]) dark += 1;
  }
  const ratio = (dark * 100) / (size * size);
  penalty += Math.floor(Math.abs(ratio - 50) / 5) * 10;
  return penalty;
}

function qrMatrix(text) {
  const bytes = qrTextBytes(text);
  if (!bytes.length) return null;
  const version = qrPickVersion(bytes.length);
  if (!version) return null;
  const stream = qrInterleave(qrDataCodewords(bytes, version), version);
  const template = qrTemplate(version);
  let best = null;
  let bestPenalty = Infinity;
  for (let mask = 0; mask < 8; mask += 1) {
    const grid = qrCloneGrid(template);
    qrPlaceData(grid, stream, mask);
    qrPlaceFormatInfo(grid, mask);
    const penalty = qrPenalty(grid);
    if (penalty < bestPenalty) {
      bestPenalty = penalty;
      best = grid;
    }
  }
  return { version, size: best.length, rows: best };
}

function qrPathData(matrix, quiet) {
  if (!matrix) return "";
  const margin = quiet === undefined ? QR_QUIET_ZONE : quiet;
  const parts = [];
  for (let row = 0; row < matrix.size; row += 1) {
    let start = -1;
    for (let column = 0; column <= matrix.size; column += 1) {
      const dark = column < matrix.size && matrix.rows[row][column] === 1;
      if (dark && start < 0) start = column;
      if (!dark && start >= 0) {
        parts.push(`M${start + margin} ${row + margin}h${column - start}v1h-${column - start}z`);
        start = -1;
      }
    }
  }
  return parts.join("");
}

function qrCanvasSize(matrix, quiet) {
  const margin = quiet === undefined ? QR_QUIET_ZONE : quiet;
  return matrix ? matrix.size + margin * 2 : 0;
}
