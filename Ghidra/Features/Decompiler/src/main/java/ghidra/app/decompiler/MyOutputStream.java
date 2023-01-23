package ghidra.app.decompiler;

import java.io.IOException;
import java.io.OutputStream;
import java.util.ArrayList;

public class MyOutputStream extends OutputStream {

	
	ArrayList<Integer> buffer = new ArrayList<>();
	private OutputStream stream;
	public MyOutputStream(OutputStream outputStream) {
		stream = outputStream;
	}


	@Override
	public void write(int b) throws IOException {
		stream.write(b);
		buffer.add(b);
	}

	@Override
	public void flush() throws IOException { stream.flush(); } 
	@Override
	public void close() throws IOException { stream.close(); }
	
	public String getBuffer() { return MyInputStream.convertBuffer(buffer); }
	public void clearBuffer() { buffer.clear(); }
}
