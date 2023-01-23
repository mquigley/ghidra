package ghidra.app.decompiler;

import java.io.ByteArrayOutputStream;

public class Num
{
	public static String zeroPad(Object value, int digits)
	{
		String string = "00000000000000000" + value;
		return string.substring(string.length() - digits);
	}

	/**
	 * Return a number in upper-case hexadecimal form.
	 *
	 * @param number Integer number.
	 * @param digits Number of digits, from 1 to 8.
	 * @return hex(255, 4) returns {@code "00FF"}.
	 */
	public static String hex(int number, int digits)
	{
		String value = "00000000" + Integer.toHexString(number).toUpperCase();
		return value.substring(value.length() - digits);
	}

	/**
	 * Return a number in upper-case hexadecimal form.
	 *
	 * @param number Integer number.
	 * @param digits Number of digits, 1 to 16.
	 * @return hex(255L, 4) returns {@code "00FF"}.
	 */
	public static String hex(long number, int digits)
	{
		String value = "0000000000000000" + Long.toHexString(number).toUpperCase();
		return value.substring(value.length() - digits);
	}

	/** Return a number in upper-case hexadecimal form. */
	public static String hex(byte number) {
		return hex(number & 0xFF);
	}

	/** Return a number in upper-case hexadecimal form. */
	public static String hex(short number) {
		return hex(number & 0xFFFF);
	}

	/** Return a number in upper-case hexadecimal form. */
	public static String hex(int number)
	{
		return Integer.toHexString(number).toUpperCase();
	}

	/** Return a number in upper-case 2-digit hexadecimal form. */
	public static String hx2(int number) {
		return hex(number, 2);
	}

	/** Return a number in upper-case 2-digit hexadecimal form. */
	public static String hx2(long number) {
		return hex(number, 2);
	}

	/** Return a number in upper-case hexadecimal form. */
	public static String hex(long number)
	{
		return Long.toHexString(number).toUpperCase();
	}

	/** Return a number in C-notation hexadecimal form, such as {@code "0x100"}. */
	public static String hexC(int number)
	{
		return "0x" + hex(number);
	}

	/** Return a number in C-notation hexadecimal form, such as {@code "0x100"}. */
	public static String hexC(long number)
	{
		return "0x" + hex(number);
	}

	/**
	 * Return a number in a disassembler's hexadecimal form, such as {@code "0"} or {@code "0Ah"}.
	 */
	public static String hexAsm(int number)
	{
		return hexAsm(number, 0);
	}

	/**
	 * Return a number in a disassembler's hexadecimal form, such as {@code "0"} or {@code "0Ah"}.
	 *
	 * @param digits How many digits should be in the hexadecimal number. 0 means not specified.
	 */
	public static String hexAsm(int number, int digits)
	{
		return hexAsm(number, digits, false);
	}

	/**
	 * Return a number in a disassembler's hexadecimal form, such as {@code "0"} or {@code "0Ah"}.
	 *
	 * @param digits How many digits should be in the hexadecimal number. 0 means not specified.
	 * @param signed If true, then print negative values
	 */
	public static String hexAsm(int number, int digits, boolean signed)
	{
		boolean negate = false;
		String toRet = "";
		if (signed && number < 0) {
			negate = true;
			number = -number;
		}

		if (number >= 0 && number <= 9)
			toRet = Integer.toHexString(number);
		else {
			if (digits <= 0)
				toRet += hex(number) + "h";
			else
				toRet += hex(number, digits) + "h";

			if (!Character.isDigit(toRet.charAt(0)))
				toRet = "0" + toRet;
		}
		if (negate)
			toRet = "-" + toRet;

		return toRet;
	}

	/**
	 * Return a number in a disassembler's hexadecimal form, such as {@code "0"} or {@code "0Ah"}.
	 *
	 * @param digits How many digits should be in the hexadecimal number. 0 means not specified.
	 */
	public static String hexAsm(long number, int digits)
	{
		if (number >= 0 && number <= 9)
			return Integer.toHexString((int) number);

		String toRet;
		if (digits <= 0)
			toRet = hex(number) + "h";
		else
			toRet = hex(number, digits) + "h";
		if (!Character.isDigit(toRet.charAt(0)))
			return "0" + toRet;
		else
			return toRet;
	}

	public static String binary8(int number) {
		return binary(number, 8);
	}

	public static String binary(int number) {
		return Integer.toBinaryString(number);
	}

	public static String binary(int number, int digits) {
		String value = "0000000000000000" + Integer.toBinaryString(number);
		return value.substring(value.length() - digits);
	}

	public static String binary(long number, int digits) {
		String value = "00000000000000000000000000000000" + Long.toBinaryString(number);
		return value.substring(value.length() - digits);
	}

	/**
	 * Returns true if the given string can be turned into a number, i.e. 0eh or 32. If there is no h or b suffix, or 
	 * 0x prefix, then presumes is base 10.
	 * 
	 * @see #intFromStr(String)
	 */
	public final static boolean IsNumber(String s)
	{
		try {
			intFromStr(s);
			return true;
		}
		catch (NumberFormatException nfe) {
			return false;
		}
	}

	public final static boolean isHex(String s)
	{
		try {
			intFromHexStr(s);
			return true;
		}
		catch (Exception e) {
			return false;
		}
	}

	public final static int intFromHexStr(String s)
	{
		if (s.endsWith("h") || s.endsWith("H"))
			s = s.substring(0, s.length() - 1);
		if (s.startsWith("0x") || s.startsWith("0X"))
			s = s.substring(2);
		return Integer.parseInt(s, 16);
	}

	/** Presumes anything ending with 'h' is a hex string; otherwise base 10 */
	public final static int intFromStr(String s) throws NumberFormatException
	{
		if (s.startsWith("0x")) {
			return Integer.parseInt(s.substring(2), 16);
		}

		if (s.endsWith("h")) {
			String s2 = s.substring(0, s.length() - 1);
			return (Integer.parseInt(s2, 16));
		}

		if (s.endsWith("b")) {
			String s2 = s.substring(0, s.length() - 1);
			return Integer.parseInt(s2, 2);
		}

		return (Integer.parseInt(s, 10));
	}

	/** Return the value of a number coded in an assembly char, such as 'A' or 'MZ'. */
	public static int intFromChar(String token) throws NumberFormatException
	{
		if (token.length() >= 3 && token.startsWith("'") && token.endsWith("'")) {
			int value = 0;
			for (int i = 1; i < token.length() - 1; i++) {
				char c = token.charAt(i);
				value = (value << 8) + c;
			}
			return value;
		}
		throw new NumberFormatException("Cannot turn " + token + " into a number");
	}

	/**
	 * Convert a signed byte to an unsigned integer.
	 *
	 * @param value A byte (-128 to 127)
	 * @return An integer (0 to 255).
	 */
	public final static int toInt(byte value)
	{
		return value & 0xFF;
	}

	public static String hexes(byte[] bytes)
	{
		return hexes(bytes, 0, bytes.length);
	}

	public static String hexes(byte[] bytes, int start, int count)
	{
		StringBuilder sb = new StringBuilder();
		for (int i = start; i < start + count; i++) {
			if (i != start)
				sb.append(' ');
			sb.append(hex(bytes[i], 2));
		}
		return sb.toString();
	}

	public static byte[] hexesToBytes(String text) {
		ByteArrayOutputStream baos = new ByteArrayOutputStream();
		for (int i = 0; i < text.length(); i++) {
			String c1 = text.substring(i, i+1);
			int v = Num.parseHex(c1);
			if (v == -1) continue;
			int v2 = -1;

			if (i < text.length() - 1) {
				i++;
				v2 = Num.parseHex(text.substring(i, i+1));
			}

			if (v2 == -1) {
				baos.write(i);
			} else {
				baos.write((v << 4) + v2);
			}
		}
		return baos.toByteArray();
	}

	public static int[] byteArrayToIntArray(byte[] array) {
		int[] target = new int[array.length];
		for (int i = 0; i < array.length; i++) {
			target[i] = array[i] & 0xFF;
		}
		return target;
	}

	/** Must be a hexadecimal. */
	public static long parseAddress(String input)
	{
		try {
			if (input == null)
				return -1;
			if (input.startsWith("0x"))
				return Long.parseLong(input.substring(2), 16);
			if (input.endsWith("h"))
				return Long.parseLong(input.substring(0, input.length() - 1), 16);
			return Long.parseLong(input, 16);
		}
		catch (Exception e) {
			return -1;
		}
	}

	/** Parse a number. Tries to decode multiple formats such as 0x1234, 1234, 12AB, 12ABh. */
	public static int parseInt(String text) throws NumberFormatException
	{
		text = text.trim();
		if (text.startsWith("0x"))
			return Integer.parseInt(text.substring(2), 16);
		if (text.endsWith("h") || text.endsWith("H"))
			return Integer.parseInt(text.substring(0, text.length() - 1), 16);

		// First try an decimal, then a hexadecimal
		try {
			return Integer.parseInt(text);
		} catch (NumberFormatException e) {
			return Integer.parseInt(text, 16);
		}
	}

	/** Parse a hexadecimal number as an integer. Tries to decode multiple formats such as 0x1234, 12AB, 12ABh. Return -1 if not hex number. */
	public static int parseHex(String text)
	{
		text = text.trim();
		if (text.startsWith("0x"))
			return Integer.parseInt(text.substring(2), 16);
		if (text.endsWith("h") || text.endsWith("H"))
			return Integer.parseInt(text.substring(0, text.length() - 1), 16);

		// No modifiers
		try {
			return Integer.parseInt(text, 16);
		} catch (NumberFormatException e) {
			return -1;
		}
	}

	/** Parse a hexadecimal number as a long. Tries to decode multiple formats such as 0x1234, 12AB, 12ABh. Return -1 if not hex number. */
	public static long parseHexL(String text)
	{
		text = text.trim();
		if (text.startsWith("0x"))
			return Long.parseLong(text.substring(2), 16);
		if (text.endsWith("h") || text.endsWith("H"))
			return Long.parseLong(text.substring(0, text.length() - 1), 16);

		// No modifiers
		try {
			return Long.parseLong(text, 16);
		} catch (NumberFormatException e) {
			return -1;
		}
	}


	/** Parse a number. Tries to decode multiple formats such as 0x1234, 1234, 12AB, 12ABh. */
	public static long parseLong(String text) throws NumberFormatException
	{
		text = text.trim();
		if (text.startsWith("0x"))
			return Long.parseLong(text.substring(2), 16);
		if (text.endsWith("h") || text.endsWith("H"))
			return Long.parseLong(text.substring(0, text.length() - 1), 16);

		// First try an decimal, then a hexadecimal
		try {
			return Long.parseLong(text);
		} catch (NumberFormatException e) {
			return Long.parseLong(text, 16);
		}
	}

	/** Parse a number. Handles strings that begin with 0b. */
	public static int parseBinary(String text) throws NumberFormatException {
		text = text.trim();
		if (text.startsWith("0b"))
			text = text.substring(2);
		return Integer.parseInt(text, 2);
	}

	public static int add16(int i1, int i2) {
		return (i1 + i2) & 0xFFFF;
	}
}
