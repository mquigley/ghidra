package ghidra.app.decompiler;

import java.io.IOException;
import java.io.InputStream;

public class MyInputStream extends InputStream {

	private InputStream stream;
	
	String buffer = "";

	public MyInputStream(InputStream inputStream) {
		stream = inputStream;
	}

	@Override
	public int read() throws IOException {
		
		int x = stream.read();
		if (x >= 32 && x <= 127) 
			buffer += (char)(x) + ", ";
		else
			buffer += hex(x) + ", ";
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
	
	public String getBuffer() { return buffer; }
	public void clearBuffer() { buffer = ""; }

	public static String hex(int x) {
		var s = Integer.toHexString(x);
		if (s.length() == 1) s = "0" + s;
		else if (s.length() > 2) s = "-" + s.substring(s.length() - 2, s.length());
		
		return s;
	}
}
