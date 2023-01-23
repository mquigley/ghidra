package ghidra.app.decompiler;

import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.StringTokenizer;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class Strings
{
	private static String SPACES = "                                                                             ";

	/** Return true if two strings are equal, checking for null. */
	public static boolean strEqual(String str1, String str2)
	{
		if (str1 == null)
			return null == str2;
		else
			return str1.equals(str2);
	}

	/**
	 * Return true if the given {@code text} is {@code null} or of length 0.
	 *
	 * @see #isBlank(String)
	 */
	public static boolean isEmpty(String text)
	{
		return text == null || text.isEmpty();
	}

	/**
	 * Return true if the given {@code text} is not {@code null} and has a length greater than 0.
	 *
	 * @see #isNotBlank(String)
	 */
	public static boolean isNotEmpty(String text)
	{
		return text != null && !text.isEmpty();
	}

	/**
	 * Return true if the given {@code string} is {@code null} or is all whitespace (i.e. of length 0 when trimmed).
	 *
	 * @see #isEmpty(String)
	 */
	public static boolean isBlank(String string)
	{
		return string == null || string.trim().isEmpty();
	}

	/**
	 * Return true if the given {@code string} is not {@code null} and is not all whitespace (i.e. of length greater
	 * than 0 when trimmed).
	 *
	 * @see #isEmpty(String)
	 */
	public static boolean isNotBlank(String string)
	{
		return string != null && !string.trim().isEmpty();
	}

	/**
	 * Remove all occurrences of '\t' and replace it with an appropriate amount of spaces, where a tab is four
	 * characters.
	 */
	public static String untabify(String line)
	{
		StringBuilder sb = new StringBuilder();
		for (int i = 0; i < line.length(); i++) {
			char c = line.charAt(i);
			if (c == '\t') {
				int length = sb.length() % 4;
				sb.append("    ".substring(length));
			} else {
				sb.append(c);
			}
		}
		return sb.toString();
	}

	/** If the given {@code string} is not {@code len} long, add spaces to make it {@code len} long. */
	public static String spaceTo(String string, int len)
	{
		return spaceTo(string, len, false);
	}

	/** If the given {@code string} is not {@code len} long, add spaces to make it {@code len} long. */
	public static String spaceTo(String string, int len, boolean requireSpace)
	{
		if (string.length() < len)
			return string + spaces(len - string.length());
		else
			return string + (requireSpace ? " " : "");
	}

	/**
	 * If the given {@code string} is not {@code len} long, return enough spaces to make it {@code len} long.
	 *
	 * @param string The string to test against.
	 * @param len The desired length.
	 * @param atLeastOneSpace If true, always return at least a space if the given {@code string} is already long
	 *            enough.
	 */
	public static String spacesFor(String string, int len, boolean atLeastOneSpace)
	{
		if (len > string.length())
			return spaces(len - string.length());
		else
			return atLeastOneSpace ? " " : "";
	}

	/** Return a sequence of {@code length} spaces. */
	public static String spaces(int length)
	{
		if (length < 0)
			return "";

		// Grow as necessary
		while (length > SPACES.length())
			SPACES += SPACES;

		return SPACES.substring(0, length);
	}

	/** Return the text, but only return at most {@code length} characters. */
	public static String atMost(String text, int length)
	{
		if (text == null)
			return "";

		if (text.length() > length && length > 3) {
			return text.substring(0, length - 3) + "...";
		}
		return text;
	}

	/** Return up to the last {@code length} characters of a string. */
	public static String suffix(String string, int length)
	{
		if (string.length() > length) {
			return string.substring(string.length() - length);
		}
		return string;
	}

	/**
	 * Returns the substring past the last period, or just the string if no periods. For example,
	 * {@code "com.package.Class"} is returned as {@code "Class"}.
	 */
	public static String stripBeforeLastPeriod(String string)
	{
		int period = string.lastIndexOf('.');
		if (period > -1) {
			return string.substring(period + 1);
		}
		return string;
	}

	/** If the given string is null, return "", otherwise return the given string. */
	public static String notNull(String string)
	{
		return string == null ? "" : string;
	}

	/**
	 * Split the given {@code from} string by the given {@code delim}. Accounts for empty areas between strings. For
	 * example, {@code split("a||b|", "|");} returns {@code "a", "", "b", ""}.
	 */
	public static ArrayList<String> splitToList(String from, String delim) {
		ArrayList<String> list = new ArrayList<>();

		int current = 0;
		while (current < from.length()) {
			int next = from.indexOf(delim, current);
			if (next == current) {
				list.add("");
			} else if (next > current) {
				list.add(from.substring(current, next));
			} else {
				if (current < from.length())
					list.add(from.substring(current, from.length()));
				break;
			}
			current = next + delim.length();
		}

		return list;
	}

	public static String splitEvery(String text, int splitBy)
	{
		if (text.length() <= splitBy)
			return text;
		StringBuilder sb = new StringBuilder((int) (text.length() * 1.3));

		StringTokenizer st = new StringTokenizer(text, " \t\n\r\f,");
		StringBuilder line = new StringBuilder(splitBy + 3);

		while (st.hasMoreTokens()) {
			String token = st.nextToken();
			if (line.length() != 0)
				line.append(", ");
			if (token.length() + line.length() > splitBy) {
				if (sb.length() != 0)
					sb.append("\n");
				sb.append(line.toString());
				line = new StringBuilder(splitBy + 3);
				line.append(token);
			} else {
				line.append(token);
			}
		}
		if (line.length() > 0) {
			sb.append("\n");
			sb.append(line);
		}

		if (false)
			for (int i = 0; i < text.length(); i += splitBy) {
				int endIndex = i + splitBy;
				if (endIndex > text.length())
					endIndex = text.length();
				if (sb.length() != 0)
					sb.append("\n");
				sb.append(text.substring(i, endIndex));
			}
		return sb.toString();
	}

	/** Return the string between the two tokens, i.e. {@code between("ab(cd)e", "(", ")")} returns {@code "cd"}. */
	
	public static String between(String text, String left, String right)
	{
		return text.substring(text.indexOf(left) + 1, text.indexOf(right));
	}

	/** Return the given {@code string} appended together {@code count} times. */
	
	public static String multiply(String string, int count)
	{
		StringBuilder sb = new StringBuilder(count);
		for (int i = 0; i < count; i++) {
			sb.append(string);
		}
		return sb.toString();
	}

	/** Combine the given collection with the given combiner. For example, {@code combine(", ", "a", "b");} returns {@code "a, b"}. */
	
	public static String combine(String combiner, boolean includeNulls, Collection<?> values) {
		StringBuilder toRet = new StringBuilder();
		for (Object s : values) {
			if (!includeNulls && s == null) continue;
			if (toRet.length() > 0)
				toRet.append(combiner);
			toRet.append(s);
		}
		return toRet.toString();
	}

	/** Combine the given collection with the given combiner. For example, {@code combine(", ", "a", "b");} returns {@code "a, b"}. */
	
	public static String combine(String combiner, Collection<?> values) {
		return combine(combiner, false, false, values);
	}


	/** Combine the given collection with the given combiner. For example, {@code combine(", ", "a", "b");} returns {@code "a, b"}. */
	
	public static String combine(String combiner, boolean includeNulls, boolean includeEmpties, Collection<?> values) {
		StringBuilder toRet = new StringBuilder();
		for (Object s : values) {
			if (!includeNulls && s == null) continue;
			if (!includeEmpties && s != null && s.toString().isEmpty()) continue;
			if (toRet.length() > 0)
				toRet.append(combiner);
			toRet.append(s);
		}
		return toRet.toString();
	}

	/** Combine the given collection with the given combiner. For example, {@code combine(", ", "a", "b");} returns {@code "a, b"}. */
	
	public static String combine(String combiner, boolean includeNulls, boolean includeEmpties, Object... values) {
		StringBuilder toRet = new StringBuilder();
		for (Object s : values) {
			if (!includeNulls && s == null) continue;
			if (!includeEmpties && s != null && s.toString().isEmpty()) continue;
			if (toRet.length() > 0)
				toRet.append(combiner);
			toRet.append(s);
		}
		return toRet.toString();
	}

	/** Combine the given strings with the given combiner. For example, {@code combine(", ", "a", "b");} returns {@code "a, b"}. */
	
	public static String combine(String combiner, String... strings) {
		StringBuilder toRet = new StringBuilder();
		for (Object s : strings) {
			if (toRet.length() > 0)
				toRet.append(combiner);
			toRet.append(s);
		}
		return toRet.toString();
	}

	/** Append the given {@code toAdd} to the existing {@code text}, prefixed with a comma if {@code text} is not empty. */
	
	public static String commaIfNeeded(String text, String toAdd)
	{
		if (text.isEmpty())
			return toAdd;
		else
			return text + "," + toAdd;
	}

	public static String spacePostIfOccuppied(String text)
	{
		if (text != null && !text.isEmpty())
			return text + " ";
		else
			return text;
	}

	public static String spacePreIfOccuppied(String text)
	{
		if (text != null && !text.isEmpty())
			return " " + text;
		else
			return text;
	}

	public static String appendWithSeparator(String source, String add, String separator)
	{
		if (isEmpty(source))
			return add;
		else
			return source + separator + add;
	}

	public static String setCharAt(String text, int i, char c) {
		StringBuilder sb = new StringBuilder(text);
		sb.setCharAt(i, c);
		return sb.toString();
	}

	/** Return an array of two. DEFghiJKL returns ["DEF", "ghiJKL"]. abcDEFghi returns ["", "abcDEFghi]. */
	public static String[] splitByCapitalized(String v)
	{
		String[] vv = new String[2];
		vv[0] = "";
		vv[1] = "";

		for (int i = 0; i < v.length(); i++) {
			if (Character.isUpperCase(v.charAt(i)))
				vv[0] += v.charAt(i);
			else
				vv[1] += v.charAt(i);
		}
		return vv;
	}

	/** Split abcDEFghi into abcDEF and ghi. */
	public static String[] splitAfterFirstCapitalizedGroup(String v)
	{
		String[] vv = new String[2];
		vv[0] = "";
		vv[1] = "";
		int state = 0;

		for (int i = 0; i < v.length(); i++) {
			char ch = v.charAt(i);
			switch (state) {
			case 0: // first part, add to first until finding uppercase
				vv[0] += ch;
				if (Character.isUpperCase(ch)) {
					state = 1;
				}
				break;
			case 1: // found uppercase
				if (Character.isLowerCase(ch) || ch == '¥') {
					state = 2;
					vv[1] += ch;
				} else {
					vv[0] += ch;
				}
				break;
			case 2: // lowercase part
				vv[1] += ch;
				break;
			}
		}
		return vv;
	}

	/** Return the first word (i.e. before the first whitespace), or the value itself if no whitespace. */
	public static String firstWord(String value)
	{
		if (value == null)
			return value;
		for (int i = 0; i < value.length(); i++) {
			if (Character.isWhitespace(value.charAt(i))) {
				return value.substring(0, i);
			}
		}

		return value;
	}
	
	/** Given the regular expression regEx, match against the given string and turn the matched groups into an array. */
	public static String[] match(String regEx, String string)
	{
		Matcher matcher = Pattern.compile(regEx).matcher(string);
		matcher.find();
		String[] values = new String[matcher.groupCount()];
		for (int i = 0; i < values.length; i++) {
			try {
				values[i] = matcher.group(i + 1).trim();
			} catch (Exception e) {
				// System.err.println("Could not find index {} from {} in {}", i, regEx, string);
			}
		}
		return values;
	}

	/** Replace all whitespace characters with a single space. For example, {@code "A  B"} turns into {@code "A B"}.
	 * @see #removeWhitespace(String) */
	public static String normalizeWhitespace(String value) {
		if (value == null)
			return null;
		return value.replaceAll("\\s+", " ");
	}

	/** Remove all whitespace characters. For example, {@code " A  B"} turns into {@code "AB"}.
	 * @see #normalizeWhitespace */
	public static String removeWhitespace(String value) {
		if (value == null)
			return null;
		return value.replaceAll("\\s+", "");
	}

	public static String hexAndBin(int... bytes) {
		StringBuilder t = new StringBuilder();
		for (int b : bytes) {
			t.append(Num.hx2(b)).append("|").append(Num.binary8(b)).append(" ");
		}
		return t.toString().trim();
	}

	public static List<String> toList(String value)
	{
		StringTokenizer st = new StringTokenizer(value, " ,");
		ArrayList<String> list = new ArrayList<>();
		while (st.hasMoreTokens()) {
			list.add(st.nextToken());
		}
		return list;
	}

	/** Given the string {@code "[A, B, C]"} return {@code List<String>[A, B, C]}. */
	public static List<String> stringToList(String value) {
		List<String> list = new ArrayList<>();
		if (value == null)
			return list;
		if (value.startsWith("[") && value.endsWith("]")) {
			value = value.substring(1, value.length() - 1);
		}
		return toList(value);
	}

	
	public static String findWordInLine(String line, int docCursorX) {
		if (line == null || line.isEmpty())
			return "";
		if (docCursorX >= line.length() || docCursorX < 0)
			return "";

		char c = line.charAt(docCursorX);
		if (Character.isJavaIdentifierPart(c)) {
			int left = docCursorX;
			int right = docCursorX;
			while (left > 0 && Character.isJavaIdentifierPart(line.charAt(left - 1))) {
				left--;
			}
			while (right < line.length() - 1 && Character.isJavaIdentifierPart(line.charAt(right + 1))) {
				right++;
			}
			return line.substring(left, right + 1);
		}

		return "";
	}

	public static boolean isJavaIdentifier(String line) {
		if (line == null || line.isEmpty())
			return false;

		char c = line.charAt(0);
		if (!Character.isJavaIdentifierStart(c))
			return false;

		int word = 1;
		int right = line.length();
		while (word < right) {
			if (!Character.isJavaIdentifierPart(line.charAt(word)))
				return false;
			word++;
		}
		return true;
	}

	public static String htmlFilter(String text) {
		StringBuilder sb = new StringBuilder(text.length() + 30);
		for (int i = 0; i < text.length(); i++) {
			char c = text.charAt(i);
			switch (c) {
				case '<': sb.append("&lt;"); break;
				case '>': sb.append("&gt;"); break;
				case '&': sb.append("&amp;"); break;
				case '\n': sb.append("<br/>"); break;
				case ' ': sb.append("&nbsp;"); break;
				default: sb.append(c); break;
			}
		}
		return sb.toString();
	}


//	private fun findWordInLine(line: String, docCursorX: Int): String {
//	if (line.isEmpty())
//		return ""
//	if (docCursorX >= line.length || docCursorX < 0)
//		return ""
//
//	val c = line[docCursorX]
//	if (Character.isJavaIdentifierPart(c)) {
//		var left = docCursorX
//		var right = docCursorX
//		while (left > 0 && Character.isJavaIdentifierPart(line[left - 1])) {
//			left--
//		}
//		while (right < line.length - 1 && Character.isJavaIdentifierPart(line[right + 1])) {
//			right++
//		}
//		return line.substring(left, right + 1)
//	}
//
//	return c.toString()
//}

}
