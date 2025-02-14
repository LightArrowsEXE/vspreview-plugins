from vstools import SPath, SPathLike, vs

__all__ = [
    'dump_pcm',
]


def dump_pcm(pcm_node: vs.AudioNode, file_path: SPathLike) -> SPath:
    """
    Dump PCM audio track to WAV file.

    :param pcm_node:    A VapourSynth AudioNode
    :param file_path:   Path to save the WAV file

    :return:            Path to the saved WAV file
    """

    sfile_path = SPath(file_path).with_suffix('.wav')

    with open(sfile_path, 'wb') as f:
        # Write WAV header
        f.write(b'RIFF')
        f.write(b'\x00\x00\x00\x00')  # File size placeholder
        f.write(b'WAVE')

        # Write format chunk
        f.write(b'fmt ')
        f.write(int.to_bytes(16, 4, 'little'))  # Chunk size
        f.write(int.to_bytes(1, 2, 'little'))  # PCM format
        f.write(int.to_bytes(pcm_node.channels, 2, 'little'))  # Channels
        f.write(int.to_bytes(pcm_node.sample_rate, 4, 'little'))  # Sample rate

        block_align = pcm_node.channels * pcm_node.bits_per_sample // 8
        byte_rate = pcm_node.sample_rate * block_align

        f.write(int.to_bytes(byte_rate, 4, 'little'))  # Byte rate
        f.write(int.to_bytes(block_align, 2, 'little'))  # Block align
        f.write(int.to_bytes(pcm_node.bits_per_sample, 2, 'little'))  # Bits per sample

        # Write data chunk
        f.write(b'data')
        f.write(b'\x00\x00\x00\x00')  # Data size placeholder

        # Write audio data
        data_size = 0
        for frame in pcm_node.frames():
            data = bytes(frame[0])
            f.write(data)
            data_size += len(data)

        # Update file size and data size
        f.seek(4)
        f.write(int.to_bytes(data_size + 36, 4, 'little'))  # File size
        f.seek(40)
        f.write(int.to_bytes(data_size, 4, 'little'))  # Data size

    return sfile_path
