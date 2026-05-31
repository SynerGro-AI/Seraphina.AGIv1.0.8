// lib/roman-wheel.js
// Roman Decoder Wheel for Glyph Language Engine

class RomanDecoderWheel {
  constructor(position, baseFreq, modulation) {
    this.position = position;
    this.baseFreq = baseFreq;
    this.modulation = modulation;
  }

  geometricSeed(inputStr) {
    const num = parseInt(inputStr, 10) || 0;
    let transformed = (num * this.baseFreq) % this.modulation;
    const romanMap = { i:1, v:5, x:10, l:50, c:100, d:500, m:1000 };
    let romanBonus = 0;
    for (let char of this.position.toLowerCase()) {
      romanBonus += romanMap[char] || 0;
    }
    return Math.floor((transformed + romanBonus) % (this.modulation * 2));
  }

  decodeData(inputStr) {
    try {
      let num = BigInt(`0x${inputStr}`);
      num = (num * BigInt(this.baseFreq)) ^ BigInt(this.modulation);
      return num.toString(16).padStart(inputStr.length, '0');
    } catch {
      return inputStr;
    }
  }
}

module.exports = { RomanDecoderWheel };