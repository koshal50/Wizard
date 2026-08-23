'use client';

import { useState, useEffect } from 'react';
import { X } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { MeshGradient } from '@paper-design/shaders-react';
import { AsciiArt } from '@/components/ui/sss';
import { createClient } from '@supabase/supabase-js';

const supabase = createClient(
	process.env.NEXT_PUBLIC_SUPABASE_URL!,
	process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY || process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
);

export default function Hero() {
	const [isExpanded, setIsExpanded] = useState(false);
	const [isSubmitting, setIsSubmitting] = useState(false);
	const [submissionStatus, setSubmissionStatus] = useState<'idle' | 'success' | 'error'>('idle');

	const handleExpand = () => {
		setIsExpanded(true);
	};

	const handleClose = () => {
		setIsExpanded(false);
		setSubmissionStatus('idle');
	};

	const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
		event.preventDefault();
		setIsSubmitting(true);
		setSubmissionStatus('idle');

		const form = event.currentTarget;
		const formData = new FormData(form);
		const { error } = await supabase.from('wizard_contact_submissions').insert({
			name: String(formData.get('name') ?? '').trim(),
			email: String(formData.get('email') ?? '').trim(),
			website: String(formData.get('website') ?? '').trim() || null,
			role: String(formData.get('role') ?? '').trim() || null,
			message: String(formData.get('message') ?? '').trim() || null,
		});

		setIsSubmitting(false);
		if (error) {
			setSubmissionStatus('error');
			return;
		}

		form.reset();
		setSubmissionStatus('success');
		window.setTimeout(() => {
			setIsExpanded(false);
			setSubmissionStatus('idle');
		}, 3000);
	};

	useEffect(() => {
		if (isExpanded) {
			document.body.style.overflow = 'hidden';
		} else {
			document.body.style.overflow = 'unset';
		}
	}, [isExpanded]);

	return (
		<>
			<div className="relative flex min-h-screen flex-col items-center justify-center px-4 sm:px-6 py-12 sm:py-20">
				{/* Redshift animated ASCII background */}
					<div className="fixed inset-0 z-0 overflow-hidden bg-black">
						<AsciiArt className="pointer-events-none h-full w-full" />
					</div>

					<div className="relative z-10 isolate flex flex-col items-center gap-4 sm:gap-6 px-5 py-6 text-center">
						<h1 className="text-4xl sm:text-5xl md:text-6xl lg:text-7xl font-normal leading-[90%] tracking-[-0.03em] text-black mix-blend-exclusion max-w-2xl">
							Build with AI. Verify with Wizard.
						</h1>

						<p className="text-base sm:text-lg md:text-xl leading-[160%] text-black max-w-2xl px-4">
							Let Wizard investigate, execute, and verify your software automatically so you can build faster with confidence.
						</p>

					<AnimatePresence initial={false}>
						{!isExpanded && (
							<motion.div className="inline-block relative">
								<motion.div
									style={{
										borderRadius: '100px',
									}}
									layout
									layoutId="cta-card"
									className="absolute inset-0 bg-[#004FE5] items-center justify-center transform-gpu will-change-transform"
								></motion.div>
								<motion.button
									initial={{ opacity: 0, scale: 0.8 }}
									animate={{ opacity: 1, scale: 1 }}
									transition={{ delay: 0.2 }}
									exit={{ opacity: 0, scale: 0.8 }}
									layout={false}
									onClick={handleExpand}
									className="h-15 px-6 sm:px-8 py-3 text-lg sm:text-xl font-regular text-[#E3E3E3] tracking-[-0.01em] relative"
								>
									Talk to the Wizard team
								</motion.button>
							</motion.div>
						)}
					</AnimatePresence>
				</div>
			</div>

			<AnimatePresence initial={false}>
				{isExpanded && (
					<div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-2">
						<motion.div
							layoutId="cta-card"
							style={{
								borderRadius: '24px',
							}}
							layout
							className="relative flex h-full w-full overflow-hidden bg-[#004FE5] transform-gpu will-change-transform"
						>
							<div className="h-full w-full overflow-y-auto overscroll-contain scrollbar-hide">
								<motion.div
									initial={{ opacity: 0 }}
									animate={{ opacity: 1 }}
									className="relative z-10 flex min-h-full w-full max-w-[1100px] flex-col items-start gap-8 px-6 py-10 pb-24 sm:p-10 lg:flex-row lg:items-center lg:gap-16 lg:p-16"
								>
<div className="flex-1 flex flex-col justify-center space-y-3 w-full">
										<h2 className="text-3xl sm:text-4xl lg:text-5xl font-medium text-white leading-none tracking-[-0.03em]">
											Talk to the Wizard team
										</h2>
										<p className="text-base sm:text-lg text-white leading-[150%] pt-4">
											Whether you&apos;re a developer building with AI or a business exploring reliable AI powered software development, we&apos;d love to hear from you.
										</p>
										<p className="text-base sm:text-lg text-white leading-[150%]">
											See how Wizard can help you understand, verify, and improve your software with evidence you can trust.
										</p>
										<div className="pt-6 sm:pt-8 mt-4 sm:mt-6 border-t border-white/20">
											<p className="text-sm font-mono uppercase tracking-[0.5px] text-white/70 mb-3">Built with Wizard</p>
											<p className="text-lg sm:text-xl lg:text-2xl text-white leading-[150%]">
												&ldquo;Wizard gives our team confidence that what AI builds actually works.&rdquo;
											</p>
										</div>
									</div>

									<div className="flex-1 w-full">
										<form onSubmit={handleSubmit} className="space-y-4 sm:space-y-5">
											{/* Name Field */}
											<div>
												<label
													htmlFor="name"
													className="block text-[10px] font-mono font-normal text-white mb-2 tracking-[0.5px] uppercase"
												>
													FULL NAME *
												</label>
												<input
													type="text"
													id="name"
													name="name"
													className="w-full px-4 py-2.5 rounded-lg bg-[#001F63] border-0 text-white placeholder:text-white/50 focus:outline-none focus:ring-2 focus:ring-white/20 transition-all text-sm h-10"
												/>
											</div>

											{/* Work Email Field */}
											<div>
												<label
													htmlFor="email"
													className="block text-[10px] font-mono font-normal text-white mb-2 tracking-[0.5px] uppercase"
												>
													WORK EMAIL *
												</label>
												<input
													type="email"
													id="email"
													name="email"
													className="w-full px-4 py-2.5 rounded-lg bg-[#001F63] border-0 text-white placeholder:text-white/50 focus:outline-none focus:ring-2 focus:ring-white/20 transition-all text-sm h-10"
												/>
											</div>

<div className="flex flex-col sm:flex-row gap-4">
														<div className="flex-1">
															<label
																htmlFor="website"
																className="block text-[10px] font-mono font-normal text-white mb-2 tracking-[0.5px] uppercase"
															>
																COMPANY / PROJECT WEBSITE
															</label>
															<input
																type="url"
																id="website"
																name="website"
																className="w-full px-4 py-2.5 rounded-lg bg-[#001F63] border-0 text-white placeholder:text-white/50 focus:outline-none focus:ring-2 focus:ring-white/20 transition-all text-sm h-10"
															/>
														</div>
														<div className="sm:w-40 w-full">
															<label
																htmlFor="role"
																className="block text-[10px] font-mono font-normal text-white mb-2 tracking-[0.5px] uppercase"
															>
																YOUR ROLE
															</label>
															<select id="role" name="role" defaultValue="" className="w-full px-4 py-2.5 rounded-lg bg-[#001F63] border-0 text-white focus:outline-none focus:ring-2 focus:ring-white/20 transition-all appearance-none cursor-pointer text-sm h-10">
																<option value="" disabled>Select your role</option>
																<option value="Developer">Developer</option>
																<option value="Founder">Founder</option>
																<option value="Engineering Leader">Engineering Leader</option>
																<option value="Other">Other</option>
															</select>
														</div>
													</div>

											{/* Message Field */}
											<div>
												<label
													htmlFor="message"
													className="block text-[10px] font-mono font-normal text-white mb-2 tracking-[0.5px] uppercase"
												>
													ANYTHING ELSE?
												</label>
												<textarea
													id="message"
													name="message"
													rows={3}
													className="w-full px-4 py-3 rounded-lg bg-[#001F63] border-0 text-white placeholder:text-white/50 focus:outline-none focus:ring-2 focus:ring-white/20 transition-all resize-none text-sm"
												/>
											</div>

											{/* Submit Button */}
							<AnimatePresence mode="wait" initial={false}>
								{submissionStatus === 'error' && (
									<motion.p key="error" role="alert" initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="text-sm text-white">
										Something went wrong. Please try again.
									</motion.p>
								)}
							</AnimatePresence>
							<motion.button
								type="submit"
								disabled={isSubmitting || submissionStatus === 'success'}
								animate={{ backgroundColor: submissionStatus === 'success' ? '#19D66B' : '#FFFFFF' }}
								transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
								className="relative flex h-10 w-full items-center justify-center overflow-hidden rounded-full px-8 py-2.5 font-medium tracking-[-0.03em] text-[#0041C1] transition-colors disabled:cursor-default"
								aria-label={submissionStatus === 'success' ? 'Form submitted' : 'Submit form'}
							>
								<AnimatePresence mode="wait" initial={false}>
									{submissionStatus === 'success' ? (
										<motion.svg
											key="check"
											viewBox="0 0 28 20"
											className="h-6 w-7"
											aria-hidden="true"
										>
											<motion.path
												d="M2 10.5 9.5 18 26 2"
												fill="none"
												stroke="#FFFFFF"
												strokeWidth="3.5"
												strokeLinecap="round"
												strokeLinejoin="round"
												initial={{ pathLength: 0 }}
												animate={{ pathLength: 1 }}
												transition={{ duration: 0.65, ease: [0.65, 0, 0.35, 1] }}
											/>
										</motion.svg>
									) : (
										<motion.span key="label" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
											{isSubmitting ? 'Sending…' : 'Submit'}
										</motion.span>
									)}
								</AnimatePresence>
							</motion.button>
										</form>
									</div>
								</motion.div>
							</div>
							<motion.div
								initial={{ opacity: 0, scale: 2 }}
								animate={{ opacity: 1, scale: 1 }}
								exit={{ opacity: 0 }}
								layout={false}
								transition={{ duration: 0.15, delay: 0.05 }}
								className="absolute inset-0 z-0 h-full overflow-hidden pointer-events-none"
								style={{
									borderRadius: '24px',
								}}
							>
								<MeshGradient
									speed={1}
									colors={['#2452F1', '#022474', '#163DB9', '#0B1D99']}
									distortion={0.8}
									swirl={0.1}
									grainMixer={0}
									grainOverlay={0}
									className="inset-0 sticky top-0"
									style={{ height: '100%', width: '100%' }}
								/>
							</motion.div>

							{/* Close Button */}
							<motion.button
								onClick={handleClose}
								className="absolute right-6 top-6 z-10 flex h-10 w-10 items-center justify-center text-white bg-transparent transition-colors hover:bg-white/10 rounded-full"
								aria-label="Close"
							>
								<X className="h-5 w-5" />
							</motion.button>
						</motion.div>
					</div>
				)}
			</AnimatePresence>
		</>
	);
}
