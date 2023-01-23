package ghidra.app.decompiler;

import java.io.IOException;
import java.io.InputStream;
import java.util.ArrayList;

public class MyInputStream extends InputStream {

	private InputStream stream;
	
	ArrayList<Integer> buffer = new ArrayList<>();

	public MyInputStream(InputStream inputStream) {
		stream = inputStream;
	}

	@Override
	public int read() throws IOException {
		
		int x = stream.read();
		buffer.add(x);
		return x;
	}
	
	@Override
	public int available() throws IOException {
		return stream.available();
	}
	
	@Override
	public void close() throws IOException {
		stream.close();
	}
	
	public String getBuffer() { return convertBuffer(buffer); }
	public void clearBuffer() { buffer.clear(); }

	public static String hex(int x) {
		var s = Integer.toHexString(x);
		if (s.length() == 1) s = "0" + s;
		else if (s.length() > 2) s = "-" + s.substring(s.length() - 2, s.length());
		
		return s;
	}
	
	static String convertBuffer(ArrayList<Integer> buffer) {
		var i = 0;
		String s = "";
		while (i < buffer.size()) {
			var b = buffer.get(i);
			
			var cmd = checkCommand(buffer, i);
			if (cmd != null) {
				i += 3; // +4 but i is increased below
				s += "<" + cmd + ">";
			}
			
			// Just output byte
			else if (false && !isStrChar(b)) {
				s += Num.hx2(b);
			}
			
			// Check for string start
			else if (i + 1 < buffer.size() && isStrChar(buffer.get(i)) && isStrChar(buffer.get(i+1)) ) {
				s += '"';
				do {
					s += (char)b.intValue();
					i++;
					if (i < buffer.size()) 
						b = buffer.get(i);
					else 
						b = -1;
				} while (isStrChar(b));
				s += '"';
				i--;
			}
			
			// Just char
			else {
				s += "'" + (char)b.intValue() + "'";
			}
			
			i++;
			if (i < buffer.size()) 
				s += ", ";
			
		}
		return s;
	}

	private static String checkCommand(ArrayList<Integer> buffer, int i) {
		if (compare(buffer, i, DecompileProcess.command_start)) return "command_start";
		if (compare(buffer, i, DecompileProcess.command_end)) return "command_end";
		if (compare(buffer, i, DecompileProcess.command_4)) return "command_4";
		if (compare(buffer, i, DecompileProcess.command_5)) return "command_5";
		if (compare(buffer, i, DecompileProcess.command_6)) return "command_6";
		if (compare(buffer, i, DecompileProcess.command_7)) return "command_7";
		if (compare(buffer, i, DecompileProcess.query_response_start)) return "query_response_start";
		if (compare(buffer, i, DecompileProcess.query_response_end)) return "query_response_end";
		if (compare(buffer, i, DecompileProcess.string_start)) return "string_start";
		if (compare(buffer, i, DecompileProcess.string_end)) return "string_end";
		if (compare(buffer, i, DecompileProcess.exception_start)) return "exception_start";
		if (compare(buffer, i, DecompileProcess.exception_end)) return "exception_end";
		if (compare(buffer, i, DecompileProcess.byte_start)) return "byte_start";
		if (compare(buffer, i, DecompileProcess.byte_end)) return "byte_end";
		return null;
	}
	
	private static boolean compare(ArrayList<Integer> buffer, int i, byte[] array) {
		for (int k = 0; k < array.length; k++) {
			if (i + k >= buffer.size()) return false;
			if (array[k] != buffer.get(i + k)) return false;
		}
		return true;
	}

	private static boolean isStrChar(Integer b) {
		return b >= 32 && b <= 127;
	}
}
