package ghidra.app.decompiler;

import java.io.IOException;
import java.io.OutputStream;

public class MyOutputStream extends OutputStream {

	
	String buffer = "";
	private OutputStream stream;
	public MyOutputStream(OutputStream outputStream) {
		stream = outputStream;
	}


	@Override
	public void write(int b) throws IOException {
		stream.write(b);
		int x = b;
		if (x >= 32 && x <= 127) 
			buffer += (char)(x) + ", ";
		else
			buffer += MyInputStream.hex(x) + ", ";
	}

	@Override
	public void flush() throws IOException { stream.flush(); } 
	@Override
	public void close() throws IOException { stream.close(); }
	
	public String getBuffer() { return buffer; }
	public void clearBuffer() { buffer = ""; }
}
